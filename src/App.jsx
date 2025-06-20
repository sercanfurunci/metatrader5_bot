import React, { useState } from "react";
import Chart from "./components/Chart";
import StatusPanel from "./components/StatusPanel";

export default function App() {
  const selectedSymbol = "XAUUSD";

  // Burada isConnected state'i ve setIsConnected fonksiyonu tanımlanmalı
  const [isConnected, setIsConnected] = useState(false);

  return (
    <div
      style={{
        padding: 20,
        background: "#222",
        minHeight: "100vh",
        color: "white",
      }}
    >
      <h1>MT5 XAUUSD RSI Bot</h1>

      <StatusPanel isConnected={isConnected} />

      <Chart selectedSymbol={selectedSymbol} setIsConnected={setIsConnected} />
    </div>
  );
}
