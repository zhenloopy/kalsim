import { useState, useEffect } from "react";
import { useBookState } from "../../hooks/useBookState";
import { api } from "../../api/client";
import DataGrid, { Column } from "../shared/DataGrid";
import ContractCell from "../shared/ContractCell";
import { Position, OrderbookLevel } from "../../api/types";

export default function OrderbookTab() {
  const { positions } = useBookState();
  const [selected, setSelected] = useState<string | null>(null);
  const [bids, setBids] = useState<OrderbookLevel[]>([]);
  const [asks, setAsks] = useState<OrderbookLevel[]>([]);

  useEffect(() => {
    if (!selected) return;
    const fetch_ = () => {
      api
        .getOrderbook(selected)
        .then((ob) => {
          setBids(ob.bids);
          setAsks(ob.asks);
        })
        .catch(() => {});
    };
    fetch_();
    const interval = setInterval(fetch_, 2000);
    return () => clearInterval(interval);
  }, [selected]);

  const posColumns: Column<Position>[] = [
    { key: "contract", header: "Contract", render: (r) => <ContractCell contractId={r.contract_id} /> },
    { key: "qty", header: "Qty", align: "right", render: (r) => r.quantity },
    {
      key: "mid",
      header: "Mid",
      align: "right",
      render: (r) => {
        const isShort = r.quantity < 0;
        return (isShort ? 1 - r.current_mid : r.current_mid).toFixed(2);
      },
    },
  ];

  const bidColumns: Column<OrderbookLevel>[] = [
    {
      key: "qty",
      header: "Bid Qty",
      align: "right",
      render: (r) => r.quantity,
    },
    {
      key: "price",
      header: "Bid Price",
      align: "right",
      render: (r) => (
        <span className="text-accent-green">{r.price.toFixed(2)}</span>
      ),
    },
  ];

  const askColumns: Column<OrderbookLevel>[] = [
    {
      key: "price",
      header: "Ask Price",
      align: "left",
      render: (r) => (
        <span className="text-accent-red">{r.price.toFixed(2)}</span>
      ),
    },
    {
      key: "qty",
      header: "Ask Qty",
      align: "left",
      render: (r) => r.quantity,
    },
  ];

  return (
    <div className="flex flex-col gap-4">
      <DataGrid
        columns={posColumns}
        data={positions}
        rowKey={(r) => r.contract_id}
        onRowClick={(r) => setSelected(r.contract_id)}
        selectedKey={selected}
        compact
      />
      {selected ? (
        <div>
          <div className="text-xs text-zinc-400 mb-2">
            Orderbook: <span className="text-zinc-200"><ContractCell contractId={selected} /></span>
          </div>
          <div className="grid grid-cols-2 gap-4">
            <DataGrid
              columns={bidColumns}
              data={bids.slice(0, 15)}
              rowKey={(r) => `bid-${r.price}`}
              compact
            />
            <DataGrid
              columns={askColumns}
              data={asks.slice(0, 15)}
              rowKey={(r) => `ask-${r.price}`}
              compact
            />
          </div>
        </div>
      ) : (
        <div className="text-xs text-zinc-500">
          Select a position to view orderbook
        </div>
      )}
    </div>
  );
}
