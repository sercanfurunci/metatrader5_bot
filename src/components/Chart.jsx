import React, { useEffect, useRef } from "react";
import { createChart, CandlestickSeries, LineSeries } from "lightweight-charts";

export default function Chart({ selectedSymbol, isConnected, setIsConnected }) {
  const chartContainerRef = useRef(null);
  const wsRef = useRef(null);
  const chartRef = useRef(null);
  const seriesRef = useRef(null);
  const rsiSeriesRef = useRef(null);

  // Close fiyatlarını tutmak için ref
  const closePricesRef = useRef([]);

  // Basit RSI hesaplama fonksiyonu (14 periyot)
  function calculateRSI(closes, period = 5) {
    if (closes.length < period + 1) return null;

    let gains = 0;
    let losses = 0;

    for (let i = closes.length - period; i < closes.length; i++) {
      const diff = closes[i] - closes[i - 1];
      if (diff > 0) gains += diff;
      else losses -= diff;
    }

    const avgGain = gains / period;
    const avgLoss = losses / period;

    if (avgLoss === 0) return 100;

    const rs = avgGain / avgLoss;
    const rsi = 100 - 100 / (1 + rs);
    return rsi;
  }

  // Chart oluştur
  useEffect(() => {
    if (!chartContainerRef.current) return;

    const chart = createChart(chartContainerRef.current, {
      width: 800,
      height: 500,
      layout: {
        textColor: "white",
        background: { type: "solid", color: "#222" },
      },
      timeScale: {
        timeVisible: true,
        secondsVisible: false,
      },
    });

    // Mum grafiği
    const candlestickSeries = chart.addSeries(CandlestickSeries, {
      priceFormat: {
        type: "price",
        precision: 5,
        minMove: 0.00001,
      },
      upColor: "#26a69a",
      downColor: "#ef5350",
      borderVisible: false,
      wickUpColor: "#26a69a",
      wickDownColor: "#ef5350",
    });

    seriesRef.current = candlestickSeries;
    chartRef.current = chart;

    // RSI grafiği (alt panelde gösterilecek)
    const rsiSeries = chart.addSeries(LineSeries, {
      color: "orange",
      lineWidth: 2,
      priceScaleId: "rsi",
    });

    rsiSeriesRef.current = rsiSeries;

    const rsiGuideLine80 = chart.addSeries(LineSeries, {
      color: "#ff0000",
      lineWidth: 1,
      priceScaleId: "rsi",
    });
    rsiGuideLine80.setData([
      { time: Date.now() / 1000 - 60 * 60 * 24, value: 80 },
      { time: Date.now() / 1000 + 60 * 60 * 24, value: 80 },
    ]);

    const rsiGuideLine20 = chart.addSeries(LineSeries, {
      color: "#00ff00",
      lineWidth: 1,
      priceScaleId: "rsi",
    });
    rsiGuideLine20.setData([
      { time: Date.now() / 1000 - 60 * 60 * 24, value: 20 },
      { time: Date.now() / 1000 + 60 * 60 * 24, value: 20 },
    ]);
    // RSI için ayrı ölçek oluştur
    chart.priceScale("rsi").applyOptions({
      scaleMargins: {
        top: 0.75,
        bottom: 0.05,
      },
      borderColor: "#555",
    });

    // Resize
    const handleResize = () => {
      if (chartContainerRef.current) {
        chart.applyOptions({
          width: chartContainerRef.current.clientWidth,
        });
      }
    };

    window.addEventListener("resize", handleResize);

    return () => {
      window.removeEventListener("resize", handleResize);
      chart.remove();
    };
  }, []);

  // Sembol değişince OHLC + RSI verisi çek
  useEffect(() => {
    if (!selectedSymbol || !seriesRef.current || !rsiSeriesRef.current) return;

    fetch(`http://localhost:8000/ohlc/${selectedSymbol}?timeframe=M1&count=100`)
      .then((res) => res.json())
      .then((data) => {
        if (data.ohlc) {
          seriesRef.current.setData(data.ohlc);

          // Close fiyatlarını da doldur
          closePricesRef.current = data.ohlc.map((candle) => candle.close);
        }

        // RSI verisini ayrı çek
        fetch(
          `http://localhost:8000/rsi/${selectedSymbol}?timeframe=M1&period=5`
        )
          .then((res) => res.json())
          .then((rsiData) => {
            console.log("RSI verisi:", rsiData);
            if (rsiData && Array.isArray(rsiData)) {
              rsiSeriesRef.current.setData(rsiData);
            }
          });
      });
  }, [selectedSymbol]);

  // WebSocket ile canlı veri güncelle
  useEffect(() => {
    if (!selectedSymbol) return;

    if (wsRef.current) {
      wsRef.current.close();
    }

    const ws = new WebSocket(`ws://localhost:8000/ws/${selectedSymbol}`);
    wsRef.current = ws;

    ws.onopen = () => {
      console.log("WebSocket bağlantısı açıldı");
      setIsConnected(true);
    };

    ws.onerror = (e) => {
      console.error("WebSocket hatası:", e);
    };

    ws.onmessage = (event) => {
      console.log("Gelen veri:", event.data);

      const data = JSON.parse(event.data);
      console.log(data);
      const date = new Date(data.time * 1000);

      // Saat:dakika:saniye formatı (örnek)
      const timeStr = date.toLocaleTimeString();

      console.log("Okunabilir saat:", timeStr);
      if (data.error) {
        console.error(data.error);
        return;
      }

      if (seriesRef.current) {
        seriesRef.current.update(data);
      }

      // Close fiyatını al, fiyatlar array'ine ekle
      if (data.close) {
        closePricesRef.current.push(data.close);

        // Gereksiz büyümeyi engellemek için eski fiyatları kırp (örnek 100 adetle sınırla)
        if (closePricesRef.current.length > 100) {
          closePricesRef.current.shift();
        }

        // RSI hesapla
        const rsiValue = calculateRSI(closePricesRef.current, 5);

        // RSI verisi varsa güncelle
        if (rsiValue !== null && rsiSeriesRef.current) {
          rsiSeriesRef.current.update({
            time: data.time, // timestamp olmalı (Unix timestamp)
            value: rsiValue,
          });
        }
      }
    };

    ws.onclose = () => {
      console.log("WebSocket bağlantısı kapandı");
      setIsConnected(false);
    };

    return () => {
      ws.close();
    };
  }, [selectedSymbol, setIsConnected]);

  return (
    <div
      ref={chartContainerRef}
      style={{
        width: "100%",
        height: "500px",
        border: "1px solid #ccc",
        borderRadius: "4px",
      }}
    />
  );
}
