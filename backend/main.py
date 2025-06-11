import os
import asyncio
from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
import MetaTrader5 as mt5

load_dotenv()

MT5_LOGIN = int(os.getenv("MT5_LOGIN"))
MT5_PASSWORD = os.getenv("MT5_PASSWORD")
MT5_SERVER = os.getenv("MT5_SERVER")

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Uygulama başında bir kez initialize
if not mt5.initialize(login=MT5_LOGIN, password=MT5_PASSWORD, server=MT5_SERVER):
    print("MT5 başlatılamadı:", mt5.last_error())
    exit(1)

@app.get("/symbols")
async def get_symbols():
    symbols = mt5.symbols_get()
    symbol_list = [symbol.name for symbol in symbols]
    return {"symbols": symbol_list}

@app.get("/ohlc/{symbol}")
async def get_ohlc(symbol: str, timeframe: str = "M1", count: int = 100):
    tf_map = {
        "M1": mt5.TIMEFRAME_M1,
        "M5": mt5.TIMEFRAME_M5,
        "M15": mt5.TIMEFRAME_M15,
        "M30": mt5.TIMEFRAME_M30,
        "H1": mt5.TIMEFRAME_H1,
        "H4": mt5.TIMEFRAME_H4,
        "D1": mt5.TIMEFRAME_D1,
    }
    tf = tf_map.get(timeframe, mt5.TIMEFRAME_M1)
    rates = mt5.copy_rates_from_pos(symbol, tf, 0, count)
    if rates is None:
        return {"error": "Veri alınamadı"}
    ohlc = [
        {
            "time": int(r["time"]),
            "open": round(float(r["open"]), 5),
            "high": round(float(r["high"]), 5),
            "low": round(float(r["low"]), 5),
            "close": round(float(r["close"]), 5),
        }
        for r in rates
    ]
    return {"ohlc": ohlc}

@app.websocket("/ws/{symbol}")
async def websocket_endpoint(websocket: WebSocket, symbol: str):
    await websocket.accept()
    if not mt5.symbol_select(symbol, True):
        await websocket.send_json({"error": f"Sembol seçilemedi: {symbol}"})
        await websocket.close()
        return
    try:
        last_time = None
        while True:
            tick = mt5.symbol_info_tick(symbol)
            if tick and tick.time_msc != last_time:
                print(f"Tick ({symbol}): {tick}")
                data = {
                    "time": int(tick.time_msc // 1000),
                    "open": round(float(tick.bid), 5),
                    "high": round(float(tick.ask), 5),
                    "low": round(float(tick.bid), 5),
                    "close": round(float(tick.ask), 5)
                }
                await websocket.send_json(data)
                last_time = tick.time_msc
            await asyncio.sleep(0.1)
    except Exception as e:
        print(f"Hata: {e}")
    finally:
        try:
            await websocket.close()
        except RuntimeError:
            pass

@app.get("/rsi/{symbol}")
async def get_rsi(symbol: str, timeframe: str = "M1", period: int = 14, count: int = 100):
    tf_map = {
        "M1": mt5.TIMEFRAME_M1,
        "M5": mt5.TIMEFRAME_M5,
        "M15": mt5.TIMEFRAME_M15,
        "M30": mt5.TIMEFRAME_M30,
        "H1": mt5.TIMEFRAME_H1,
        "H4": mt5.TIMEFRAME_H4,
        "D1": mt5.TIMEFRAME_D1,
    }
    tf = tf_map.get(timeframe, mt5.TIMEFRAME_M1)
    rates = mt5.copy_rates_from_pos(symbol, tf, 0, count)

    if rates is None or len(rates) < period + 1:
        return {"error": "Yetersiz veri"}

    closes = [r['close'] for r in rates]
    rsi_values = []

    for i in range(period, len(closes)):
        gains = []
        losses = []
        for j in range(i - period, i):
            change = closes[j + 1] - closes[j]
            if change >= 0:
                gains.append(change)
                losses.append(0)
            else:
                gains.append(0)
                losses.append(abs(change))
        avg_gain = sum(gains) / period
        avg_loss = sum(losses) / period
        rs = avg_gain / avg_loss if avg_loss != 0 else 0
        rsi = 100 - (100 / (1 + rs)) if avg_loss != 0 else 100
        rsi_values.append({
            "time": int(rates[i]["time"]),
            "value": round(rsi, 2)
        })

    return {"rsi": rsi_values}


# Uygulama kapanınca shutdown
import atexit
atexit.register(mt5.shutdown)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)