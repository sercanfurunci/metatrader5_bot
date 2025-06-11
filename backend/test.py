import MetaTrader5 as mt5
import time

if not mt5.initialize():
    print("MT5 başlatılamadı:", mt5.last_error())
    quit()

symbol = "EURUSD"
while True:
    tick = mt5.symbol_info_tick(symbol)
    print("Tick:", tick)
    time.sleep(1)