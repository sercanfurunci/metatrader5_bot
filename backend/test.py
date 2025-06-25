import MetaTrader5 as mt5
import os
import time
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from dotenv import load_dotenv

# .env yükle ve bağlantı kur
load_dotenv()
login = int(os.getenv("MT5_LOGIN"))
password = os.getenv("MT5_PASSWORD")
server = os.getenv("MT5_SERVER")

if not mt5.initialize():
    print("initialize() failed:", mt5.last_error())
    quit()

if not mt5.login(login, password, server):
    print("login() failed:", mt5.last_error())
    quit()

print("✅ Bağlantı başarılı")

# RSI hesaplama fonksiyonu
def calculate_rsi(close_prices, period=5):
    delta = close_prices.diff()
    gain = delta.where(delta > 0, 0)
    loss = -delta.where(delta < 0, 0)

    avg_gain = gain.rolling(window=period).mean()
    avg_loss = loss.rolling(window=period).mean()

    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return rsi

# Dakika başında bekleyen fonksiyon
def dakika_basinda_bekle():
    now = datetime.now()
    saniye_kalani = 60 - now.second
    print(f"⏳ Yeni mum bekleniyor ({saniye_kalani} saniye)...")
    time.sleep(saniye_kalani + 2)  # tampon: terminal gecikmesine karşı

# Bot ayarları
symbol = "XAUUSD"
lot = 0.01
max_lot = 0.16
prev_signal = None
# --- DURUM ÖZETİ ---

def durum_ozeti():
    acc = mt5.account_info()
    if acc:
        print(f"💼 Bakiye: {acc.balance} | Equity: {acc.equity} | Serbest Marjin: {acc.margin_free}")
    
    positions = mt5.positions_get()
    if positions and len(positions) > 0:
        p = positions[-1]
        print(f"📈 Son Açık Pozisyon → {p.symbol} | {'BUY' if p.type == 0 else 'SELL'} | Lot: {p.volume} | Fiyat: {p.price_open} | Kâr: {p.profit}")
    else:
        print("📭 Açık pozisyon yok.")
    
    deals = mt5.history_deals_get(datetime.now() - timedelta(days=1), datetime.now())
    if deals and len(deals) > 0:
        d = deals[-1]
        print(f"🕓 Son İşlem → {d.symbol} | {'BUY' if d.type == 0 else 'SELL'} | Lot: {d.volume} | Fiyat: {d.price} | Kâr: {d.profit}")
    else:
        print("📭 Son 24 saatte işlem yok.")

durum_ozeti()


# positions = mt5.positions_get()
# if positions:
#     print(f"Açık pozisyon var: {len(positions)} adet. Kapatılıyor...")
#     for pos in positions:
#         symbol = pos.symbol
#         ticket = pos.ticket
#         volume = pos.volume
#         price = mt5.symbol_info_tick(symbol).ask if pos.type == mt5.ORDER_TYPE_SELL else mt5.symbol_info_tick(symbol).bid
#         order_type = mt5.ORDER_TYPE_BUY if pos.type == mt5.ORDER_TYPE_SELL else mt5.ORDER_TYPE_SELL

#         request = {
#             "action": mt5.TRADE_ACTION_DEAL,
#             "symbol": symbol,
#             "volume": volume,
#             "type": order_type,
#             "position": ticket,
#             "price": price,
#             "deviation": 10,
#             "magic": 123456,
#             "comment": "Pozisyon Kapatma",
#             "type_time": mt5.ORDER_TIME_GTC,
#             "type_filling": mt5.ORDER_FILLING_IOC,
#         }

#         result = mt5.order_send(request)
#         if result.retcode == mt5.TRADE_RETCODE_DONE:
#             print(f"✅ Pozisyon kapatıldı: Ticket {ticket}")
#         else:
#             print(f"❌ Pozisyon kapatma başarısız: Ticket {ticket} | Retcode: {result.retcode}")
# else:
#     print("Açık pozisyon yok.")


print("♻️ RSI botu başlatıldı. Her yeni 1 dakikalık mumda çalışacak...")
# Döngü
try:
    while True:
        dakika_basinda_bekle()

        if not mt5.symbol_select(symbol, True):
            print(f"❌ {symbol} sembolü seçilemedi.")
            continue

        rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M1, 0, 100)
        if rates is None or len(rates) < 6:
            print("❌ Mum verisi alınamadı veya yetersiz.")
            continue

        df = pd.DataFrame(rates)
        df['time'] = pd.to_datetime(df['time'], unit='s')
        df.set_index('time', inplace=True)
        df['close'] = df['close'].astype(float)
        df['rsi'] = calculate_rsi(df['close'], period=5)

        if df['rsi'].dropna().empty:
            print("❌ RSI değeri hesaplanamadı (yetersiz kapanış verisi).")
            continue

        latest_rsi = df['rsi'].dropna().iloc[-1]
        print(f"🕒 {datetime.now().strftime('%H:%M:%S')} | RSI(5): {latest_rsi:.2f}", end=" ")

        current_signal = None
        if latest_rsi > 80:
            current_signal = "BUY"
        elif latest_rsi < 20:
            current_signal = "SELL"

        if current_signal is None:
            print("| RSI sinyal bölgesinde değil, işlem yapılmadı.")
            continue

        positions = mt5.positions_get(symbol=symbol)
        open_sides = [p.type for p in positions]

      

        # Karşı sinyal geldiyse lot 2 katına çıkarılır
        if prev_signal and prev_signal != current_signal:
            lot = min(lot * 2, max_lot)
            if lot >= max_lot:
                print(f"⚠️ Maksimum lot ({max_lot}) sınırına ulaşıldı. Lot sıfırlanacak.")
                lot = 0.01
        elif prev_signal == current_signal:
            print("| Aynı sinyal tekrar etti, martingale tetiklenmedi.")
            continue
        else:
            lot = 0.01  # ilk işlemde sıfırla

        #guncel tick verisi
        tick = mt5.symbol_info_tick(symbol)
        if not tick:
            print("❌ Sembol için tick verisi alınamadı.")
            continue

        tick_time = datetime.fromtimestamp(tick.time)
        if (datetime.now() - tick_time).total_seconds() > 5:
            print(f"❌ Fiyat verisi güncel değil ({tick_time.strftime('%H:%M:%S')}) → Emir gönderilmedi.")
            continue

        # spread = tick.ask - tick.bid
        # if spread > 0.0010:
        #     print(f"⚠️ Spread çok yüksek: {spread:.5f} → Emir gönderilmedi.")
        #     continue
        price = tick.ask if current_signal == "BUY" else tick.bid

        order_type = mt5.ORDER_TYPE_BUY if current_signal == "BUY" else mt5.ORDER_TYPE_SELL

        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": lot,
            "type": order_type,
            "price": price,
            "deviation": 100,
            "magic": 123456,
            "comment": f"RSI Martingale {current_signal}",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_RETURN,
        }

        result = mt5.order_send(request)
        if result.retcode == mt5.TRADE_RETCODE_DONE:
            print(f"| ✅ {current_signal} işlemi açıldı! Lot: {lot:.2f}, Ticket: {result.order}")
            prev_signal = current_signal
        else:
            print(f"| ❌ İşlem başarısız: {result.retcode}")

except KeyboardInterrupt:
    print("\n🛑 Bot durduruldu.")
    mt5.shutdown()






