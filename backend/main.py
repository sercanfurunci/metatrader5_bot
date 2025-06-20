import os
import asyncio
from fastapi import FastAPI, WebSocket, BackgroundTasks, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
import MetaTrader5 as mt5
import atexit
from datetime import datetime, timedelta

load_dotenv()

MT5_LOGIN = int(os.getenv("MT5_LOGIN"))
MT5_PASSWORD = os.getenv("MT5_PASSWORD")
MT5_SERVER = os.getenv("MT5_SERVER")

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],  # tüm kaynaklara izin
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
# MT5 başlat
if not mt5.initialize(login=MT5_LOGIN, password=MT5_PASSWORD, server=MT5_SERVER):
    print("MT5 başlatılamadı:", mt5.last_error())
    exit(1)

# Bot durumu ve değişkenler
bot_state = {
    "bot_active": True,
    "total_profit_today": 0.0,
    "current_lot": 0.01,
    "trade_direction": None,  # "BUY" veya "SELL"
    "last_rsi_signal": None,  # "BUY" veya "SELL"
    "positions": [],
    "max_lot": 0.16,
    "profit_target": 100.0,
    "last_profit_reset": datetime.utcnow().date(),
    "no_trade_today": False,  # Kar hedefi sonrası gün sonuna kadar işlem açılmasın
}

# Yardımcı fonksiyon: RSI hesaplama (Basit, Close fiyatları ile)
def calculate_rsi(closes, period=5):
    # Kapanışlar en eski -> en yeni sırada olmalı
    if len(closes) < period + 1:
        return None
    # Son (period+1) kapanışı al
    closes = list(closes)[- (period + 1):]
    gains = []
    losses = []
    for i in range(1, period + 1):
        diff = closes[i] - closes[i - 1]
        if diff > 0:
            gains.append(diff)
            losses.append(0)
        else:
            gains.append(0)
            losses.append(-diff)
    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    rsi = 100.0 - (100.0 / (1 + rs))
    return round(rsi, 2)

# Yardımcı fonksiyon: MT5 üzerinden RSI getir
def get_rsi_value(symbol: str, timeframe: int, period: int = 5, count: int = 100):
    rates = mt5.copy_rates_from_pos(symbol, timeframe, 0, count)
    if rates is None:
        print(f"[RSI ERROR] Sembol: {symbol}, Timeframe: {timeframe}, rates=None")
        return None
    if len(rates) < period + 1:
        print(f"[RSI ERROR] Sembol: {symbol}, Timeframe: {timeframe}, Veri yetersiz! (Adet: {len(rates)})")
        return None
    closes = [r['close'] for r in rates]
    # Emin olmak için kapanışları en eski -> en yeni sırada kullanıyoruz
    # (MT5 genellikle bu sırada döner, ama garanti için dokunmuyoruz)
    print(f"[RSI DEBUG] Sembol: {symbol}, Timeframe: {timeframe}, Kapanışlar: {closes[-6:]}")
    return calculate_rsi(closes, period)

# Yardımcı fonksiyon: Tüm pozisyonları kapat
def close_all_positions():
    positions = mt5.positions_get(symbol="XAUUSD")
    if not positions:
        return 0.0

    total_profit = 0.0

    for pos in positions:
        volume = pos.volume
        close_type = mt5.ORDER_TYPE_SELL if pos.type == mt5.ORDER_TYPE_BUY else mt5.ORDER_TYPE_BUY
        price = mt5.symbol_info_tick("XAUUSD").bid if pos.type == mt5.ORDER_TYPE_BUY else mt5.symbol_info_tick("XAUUSD").ask

        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": pos.symbol,
            "volume": volume,
            "type": close_type,
            "position": pos.ticket,
            "price": price,
            "deviation": 10,
            "magic": 234000,
            "comment": "RSI Bot Kapat",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }
        result = mt5.order_send(request)
        if result.retcode == mt5.TRADE_RETCODE_DONE:
            total_profit += pos.profit

    return total_profit

# Yardımcı fonksiyon: Pozisyon aç
def open_position(direction: str):
    if bot_state.get("no_trade_today", False):
        print("[INFO] Bugün tekrar işlem açılmayacak.")
        return False
    if bot_state["last_rsi_signal"] == direction:
        # Aynı yönde işlem varsa işlem yapma
        return False
    if bot_state["trade_direction"] and bot_state["trade_direction"] != direction:
        # Trend değişmiş, lot artır (max 0.16)
        new_lot = min(bot_state["current_lot"] * 2, bot_state["max_lot"])
        bot_state["current_lot"] = new_lot
    else:
        # İlk işlem veya aynı trend devamı
        bot_state["current_lot"] = 0.01
    tick = mt5.symbol_info_tick("XAUUSD")
    if tick is None:
        print("[ERROR] Tick verisi alınamadı.")
        return False
    price = tick.ask if direction == "BUY" else tick.bid
    order_type = mt5.ORDER_TYPE_BUY if direction == "BUY" else mt5.ORDER_TYPE_SELL
    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": "XAUUSD",
        "volume": bot_state["current_lot"],
        "type": order_type,
        "price": price,
        "deviation": 10,
        "magic": 234000,
        "comment": "RSI Bot Trade",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }
    result = mt5.order_send(request)
    if result.retcode != mt5.TRADE_RETCODE_DONE:
        print(f"[ERROR] İşlem başarısız: {result.retcode}")
        return False
    bot_state["trade_direction"] = direction
    bot_state["last_rsi_signal"] = direction
    print(f"[INFO] {direction} işlemi açıldı, lot: {bot_state['current_lot']}")
    return True

# Günlük kâr reseti
def reset_daily_profit_if_needed():
    today = datetime.utcnow().date()
    if bot_state["last_profit_reset"] != today:
        bot_state["total_profit_today"] = 0.0
        bot_state["current_lot"] = 0.01
        bot_state["trade_direction"] = None
        bot_state["last_rsi_signal"] = None
        bot_state["positions"] = []
        bot_state["last_profit_reset"] = today
        bot_state["no_trade_today"] = False  # Gün başında tekrar işlem açılabilir
        print("[INFO] Günlük kar hedefi ve işlem izni resetlendi.")

# Arkaplan task: Bot mantığı (async)
async def bot_logic():
    while True:
        if bot_state["bot_active"]:
            reset_daily_profit_if_needed()
            if bot_state.get("no_trade_today", False):
                print("[INFO] Bugün tekrar işlem açılmayacak (no_trade_today aktif).")
                await asyncio.sleep(5)
                continue
            if bot_state["total_profit_today"] >= bot_state["profit_target"]:
                profit = close_all_positions()
                bot_state["total_profit_today"] += profit
                print("[INFO] Bugün hedefe ulaşıldı, işlem durduruldu.")
                bot_state["no_trade_today"] = True
                await asyncio.sleep(10)
                continue
            rsi_1m = get_rsi_value("XAUUSD", mt5.TIMEFRAME_M1, period=5)
            rsi_5m = get_rsi_value("XAUUSD", mt5.TIMEFRAME_M5, period=5)
            if rsi_1m is None or rsi_5m is None:
                print("[WARN] RSI verisi alınamadı.")
                await asyncio.sleep(5)
                continue
            print(f"[DEBUG] RSI 1m: {rsi_1m}, RSI 5m: {rsi_5m}")
            # 5dk RSI ile toplu pozisyon kapama
            if bot_state["trade_direction"] == "BUY" and rsi_5m >= 80:
                profit = close_all_positions()
                bot_state["total_profit_today"] += profit
                print(f"[INFO] 5dk RSI 80+, tüm BUY pozisyonları kapatıldı. Güncel kar: {bot_state['total_profit_today']}")
                bot_state["trade_direction"] = None
                bot_state["last_rsi_signal"] = None
                bot_state["current_lot"] = 0.01
                await asyncio.sleep(10)
                continue
            if bot_state["trade_direction"] == "SELL" and rsi_5m <= 20:
                profit = close_all_positions()
                bot_state["total_profit_today"] += profit
                print(f"[INFO] 5dk RSI 20-, tüm SELL pozisyonları kapatıldı. Güncel kar: {bot_state['total_profit_today']}")
                bot_state["trade_direction"] = None
                bot_state["last_rsi_signal"] = None
                bot_state["current_lot"] = 0.01
                await asyncio.sleep(10)
                continue
            # 1dk RSI ile işlem açma
            if rsi_1m >= 80:
                open_position("BUY")
            elif rsi_1m <= 20:
                open_position("SELL")
        await asyncio.sleep(5)  # 5 saniyede bir kontrol

# API endpointler (diğerlerin üstüne ekleyebilirsin)

@app.websocket("/ws/{symbol}")
async def websocket_endpoint(websocket: WebSocket, symbol: str):
    await websocket.accept()
    try:
        while True:
            # Örnek: her 5 saniyede RSI ve fiyat gönder
            rsi = get_rsi_value(symbol, mt5.TIMEFRAME_M1)
            tick = mt5.symbol_info_tick(symbol)
            data = {
                "rsi": rsi,
                "bid": tick.bid if tick else None,
                "ask": tick.ask if tick else None,
                "time": datetime.utcnow().isoformat(),
            }
            await websocket.send_json(data)
            await asyncio.sleep(5)
    except WebSocketDisconnect:
        print(f"WebSocket bağlantısı kesildi: {symbol}")


@app.get("/ohlc/{symbol}")
async def get_ohlc(symbol: str, timeframe: str = "M1", count: int = 100):
    tf_map = {
        "M1": mt5.TIMEFRAME_M1,
        "M5": mt5.TIMEFRAME_M5,
        "H1": mt5.TIMEFRAME_H1,
    }
    tf = tf_map.get(timeframe.upper())
    if tf is None:
        raise HTTPException(status_code=400, detail="Invalid timeframe")

    rates = mt5.copy_rates_from_pos(symbol, tf, 0, count)
    if rates is None:
        raise HTTPException(status_code=404, detail="Symbol not found or no data")

    ohlc_data = []
    for r in rates:
        ohlc_data.append({
            "time": r['time'],
            "open": r['open'],
            "high": r['high'],
            "low": r['low'],
            "close": r['close'],
            "tick_volume": r['tick_volume'],
        })
    return ohlc_data

@app.get("/rsi/{symbol}")
async def get_rsi(symbol: str, timeframe: str = "M1", period: int = 5):
    tf_map = {
        "M1": mt5.TIMEFRAME_M1,
        "M5": mt5.TIMEFRAME_M5,
        "H1": mt5.TIMEFRAME_H1,
    }
    tf = tf_map.get(timeframe.upper())
    if tf is None:
        raise HTTPException(status_code=400, detail="Invalid timeframe")

    rates = mt5.copy_rates_from_pos(symbol, tf, 0, 100)
    if rates is None or len(rates) < period + 1:
        raise HTTPException(status_code=404, detail="Symbol not found or insufficient data")

    closes = [r['close'] for r in rates]
    rsi_value = calculate_rsi(closes, period)
    return {"rsi": rsi_value}

@app.get("/status")
async def get_status():
    return bot_state

@app.post("/toggle")
async def toggle_bot(state: bool):
    bot_state["bot_active"] = state
    return bot_state

@app.get("/account")
async def get_account_info():
    info = mt5.account_info()
    if info is None:
        raise HTTPException(status_code=500, detail="MT5 account info alınamadı")
    print(info.balance)  # Hesap bakiyesi
    print(info.equity)   # Anlık toplam varlık (bakiyeye açık işlemler dahil)
    print(info.profit)   # Açık işlemlerden toplam kar/zarar
    return {
        "login": info.login,
        "balance": info.balance,
        "equity": info.equity,
        "profit": info.profit,
        "margin": info.margin,
        "margin_free": info.margin_free,
        "currency": info.currency,
        "leverage": info.leverage,
        "name": info.name,
        "server": info.server,
    }

# Background task başlat
@app.on_event("startup")
async def startup_event():
    asyncio.create_task(bot_logic())

atexit.register(mt5.shutdown)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
