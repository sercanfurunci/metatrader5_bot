import React, { useEffect, useState } from "react";
import Chart from "./components/Chart";

export default function App() {
  const [symbols, setSymbols] = useState([]);
  const [selectedSymbol, setSelectedSymbol] = useState("");
  const [isConnected, setIsConnected] = useState(false);

  // Sembolleri yükle
  useEffect(() => {
    fetch("http://localhost:8000/symbols")
      .then((response) => response.json())
      .then((data) => setSymbols(data.symbols || []))
      .catch((error) => {
        console.error("Semboller yüklenemedi:", error);
        setSymbols([]);
      });
  }, []);

  return (
    <div
      style={{
        padding: 20,
        background: "#222",
        minHeight: "100vh",
        color: "white",
      }}
    >
      <h1>MT5 Grafik Örneği</h1>

      <div style={{ marginBottom: 20 }}>
        <select
          value={selectedSymbol}
          onChange={(e) => setSelectedSymbol(e.target.value)}
          style={{ padding: "8px", fontSize: "16px" }}
        >
          <option value="">Sembol Seçin</option>
          {symbols.map((symbol) => (
            <option key={symbol} value={symbol}>
              {symbol}
            </option>
          ))}
        </select>

        <span
          style={{ marginLeft: 10, color: isConnected ? "limegreen" : "red" }}
        >
          {isConnected ? "Bağlı" : "Bağlı Değil"}
        </span>
      </div>

      <Chart
        selectedSymbol={selectedSymbol}
        isConnected={isConnected}
        setIsConnected={setIsConnected}
      />
    </div>
  );
}
