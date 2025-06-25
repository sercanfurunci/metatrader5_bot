import MetaTrader5 as mt5
import os
import time
import pandas as pd
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

# Tüm pozisyonları kapatma fonksiyonu
def tum_pozisyonlari_kapat():
    positions = mt5.positions_get()
    if not positions:
        print("📭 Kapatılacak pozisyon yok.")
        return True

    success = True
    for pos in positions:
        symbol = pos.symbol
        ticket = pos.ticket
        volume = pos.volume
        # Pozisyon türüne göre ters emir tipi
        order_type = mt5.ORDER_TYPE_SELL if pos.type == mt5.ORDER_TYPE_BUY else mt5.ORDER_TYPE_BUY
        price = mt5.symbol_info_tick(symbol).bid if order_type == mt5.ORDER_TYPE_SELL else mt5.symbol_info_tick(symbol).ask

        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": volume,
            "type": order_type,
            "position": ticket,
            "price": price,
            "deviation": 100,
            "magic": 123456,
            "comment": "Toplu Pozisyon Kapatma",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_RETURN,
        }

        result = mt5.order_send(request)
        if result.retcode == mt5.TRADE_RETCODE_DONE:
            print(f"✅ Pozisyon kapatıldı: Ticket {ticket}")
        else:
            print(f"❌ Pozisyon kapatma başarısız: Ticket {ticket} | Retcode: {result.retcode}")
            success = False
    return success

# Bot ayarları
symbol = "XAUUSD"
lot = 0.01
max_lot = 0.16
prev_signal = None
daily_profit_target = 100.0
daily_profit_reached = False
today_date = datetime.now().date()

#5 dakikalık RSI 
latest_rsi_5m = None

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

print("♻️ RSI botu başlatıldı. Her yeni 1 dakikalık mumda çalışacak...")

try:
    while True:
        # Gün değiştiyse kar durumu sıfırlanır, lot da sıfırlanır
        if datetime.now().date() != today_date:
            today_date = datetime.now().date()
            daily_profit_reached = False
            lot = 0.01
            prev_signal = None
            print("📅 Yeni güne geçildi, günlük kar durumu sıfırlandı.")

        dakika_basinda_bekle()

        if not mt5.symbol_select(symbol, True):
            print(f"❌ {symbol} sembolü seçilemedi.")
            continue

        # 1 dakikalık mum verisi
        rates_1m = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M1, 0, 100)
        if rates_1m is None or len(rates_1m) < 6:
            print("❌ 1 dakikalık mum verisi alınamadı veya yetersiz.")
            continue

        df_1m = pd.DataFrame(rates_1m)
        df_1m['time'] = pd.to_datetime(df_1m['time'], unit='s')
        df_1m.set_index('time', inplace=True)
        df_1m['close'] = df_1m['close'].astype(float)
        df_1m['rsi'] = calculate_rsi(df_1m['close'], period=5)

        if df_1m['rsi'].dropna().empty:
            print("❌ 1 dakikalık RSI değeri hesaplanamadı.")
            continue

        latest_rsi_1m = df_1m['rsi'].dropna().iloc[-1]


        
        # 5 dakikalık RSI sadece her 5 dakikada bir güncellensin
        if datetime.now().minute % 5 == 0:
            rates_5m = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M5, 0, 100)
            if rates_5m is None or len(rates_5m) < 6:
                print("❌ 5 dakikalık mum verisi alınamadı veya yetersiz.")
                continue

            df_5m = pd.DataFrame(rates_5m)
            df_5m['time'] = pd.to_datetime(df_5m['time'], unit='s')
            df_5m.set_index('time', inplace=True)
            df_5m['close'] = df_5m['close'].astype(float)
            df_5m['rsi'] = calculate_rsi(df_5m['close'], period=5)

            if df_5m['rsi'].dropna().empty:
                print("❌ 5 dakikalık RSI değeri hesaplanamadı.")
                continue

            latest_rsi_5m = df_5m['rsi'].dropna().iloc[-1]

        # Günlük karı kontrol et (son 24 saatteki kar toplamı)
        deals = mt5.history_deals_get(datetime.now() - timedelta(days=1), datetime.now())
        total_profit = 0
        if deals:
            total_profit = sum([d.profit for d in deals])
        if latest_rsi_5m is not None:
            print(f"🕒 {datetime.now().strftime('%H:%M:%S')} | 1m RSI: {latest_rsi_1m:.2f} | 5m RSI: {latest_rsi_5m:.2f} | Günlük Kar: {total_profit:.2f}", end=" ")
        else:
            print(f"🕒 {datetime.now().strftime('%H:%M:%S')} | 1m RSI: {latest_rsi_1m:.2f} | 5m RSI: ??.?? | Günlük Kar: {total_profit:.2f}", end=" ")

        # Eğer günlük kar hedefi tutmuşsa, pozisyon açma ve işlemleri durdur
        if total_profit >= daily_profit_target:
            if not daily_profit_reached:
                print(f"\n🎯 Günlük {daily_profit_target}$ kar hedefi aşıldı. Tüm pozisyonlar kapatılıyor ve yeni işlem açılmayacak.")
                if tum_pozisyonlari_kapat():
                    daily_profit_reached = True
                    lot = 0.01
                    prev_signal = None
                else:
                    print("❌ Tüm pozisyonları kapatırken hata oluştu.")
            else:
                print("| Günlük kar hedefi aşıldı, işlem açılmıyor.")
            continue

        # Eğer 5 dakikalık RSI kritik bölgede ise tüm pozisyonları kapat ve lot sıfırla
        if latest_rsi_5m is not None and (latest_rsi_5m > 80 or latest_rsi_5m < 20):
            print(f"\n⚠️ 5 Dakikalık RSI kritik seviyede ({latest_rsi_5m:.2f}). Tüm pozisyonlar kapatılıyor.")
            if tum_pozisyonlari_kapat():
                lot = 0.01
                prev_signal = None
            else:
                print("❌ Tüm pozisyonları kapatırken hata oluştu.")
            continue

        # 1 dakikalık RSI sinyalleriyle işlem açma
        current_signal = None
        if latest_rsi_1m > 80:
            current_signal = "BUY"
        elif latest_rsi_1m < 20:
            current_signal = "SELL"

        if current_signal is None:
            print("| RSI sinyal bölgesinde değil, işlem yapılmadı.")
            continue

        positions = mt5.positions_get(symbol=symbol)
        open_sides = [p.type for p in positions] if positions else []

        # Martingale lot ayarı
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

        # Güncel tick verisi
        tick = mt5.symbol_info_tick(symbol)
        if not tick:
            print("❌ Sembol için tick verisi alınamadı.")
            continue

        tick_time = datetime.fromtimestamp(tick.time)
        if (datetime.now() - tick_time).total_seconds() > 5:
            print(f"❌ Fiyat verisi güncel değil ({tick_time.strftime('%H:%M:%S')}) → Emir gönderilmedi.")
            continue

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
