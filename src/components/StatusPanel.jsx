import React, { useEffect, useState } from "react";

export default function StatusPanel() {
  const [status, setStatus] = useState(null);
  const [loading, setLoading] = useState(false);

  const fetchStatus = async () => {
    try {
      const response = await fetch("http://localhost:8000/status");
      const data = await response.json();
      setStatus(data);
    } catch {
      setStatus(null);
    }
  };

  useEffect(() => {
    fetchStatus();
    const interval = setInterval(fetchStatus, 3000);
    return () => clearInterval(interval);
  }, []);

  const handleToggleBot = async () => {
    if (!status) return;
    setLoading(true);
    try {
      const newState = !status.bot_active;
      await fetch(`http://localhost:8000/toggle?state=${newState}`, {
        method: "POST",
      });
      fetchStatus();
    } catch (error) {
      console.error("Bot durumu değiştirilemedi", error);
    } finally {
      setLoading(false);
    }
  };

  if (!status) return <p>Yükleniyor...</p>;
  const safeClosedTrades = status?.closed_trades ?? [];

  return (
    <div
      style={{
        marginBottom: 20,
        padding: 20,
        background: "#333",
        borderRadius: 8,
      }}
    >
      <p>
        Bot Aktif:{" "}
        <strong style={{ color: status?.bot_active ? "lime" : "red" }}>
          {status?.bot_active ? "Evet" : "Hayır"}
        </strong>
      </p>
      <p>
        Toplam Kar (Bugün): ${status?.total_profit_today?.toFixed(2) ?? "0.00"}
      </p>
      <p>Mevcut Lot: {status?.current_lot ?? 0}</p>
      <button
        onClick={handleToggleBot}
        disabled={loading}
        style={{
          padding: "8px 16px",
          backgroundColor: status?.bot_active ? "red" : "limegreen",
          color: "white",
          border: "none",
          cursor: "pointer",
          borderRadius: 5,
          fontWeight: "bold",
          marginTop: 10,
        }}
      >
        {status?.bot_active ? "Botu Durdur" : "Botu Başlat"}
      </button>

      <h3>Son 5 Kapanan İşlem</h3>
      <ul>
        {safeClosedTrades.length === 0 && <li>İşlem yok</li>}
        {safeClosedTrades.slice(-5).map((trade, idx) => (
          <li key={idx}>
            {trade.time} - Kar: ${trade.profit.toFixed(2)}
          </li>
        ))}
      </ul>
    </div>
  );
}
