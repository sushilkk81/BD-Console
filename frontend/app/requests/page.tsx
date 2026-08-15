"use client";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { createRequest, listRequests } from "@/lib/api";

type RequestRow = {
  id: number;
  brand: string;
  market: string;
  device: string | null;
  status: string;
  total: number;
};

export default function RequestsPage() {
  const router = useRouter();
  const [token, setToken] = useState<string | null>(null);
  const [requests, setRequests] = useState<RequestRow[]>([]);
  const [brand, setBrand] = useState("");
  const [market, setMarket] = useState("US");

  useEffect(() => {
    const t = localStorage.getItem("bdconsole_token");
    if (!t) {
      router.replace("/login");
      return;
    }
    setToken(t);
    listRequests(t).then(setRequests);
  }, [router]);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!token) return;
    await createRequest(token, { brand, market });
    setRequests(await listRequests(token));
    setBrand("");
  }

  if (!token) return null;

  return (
    <main>
      <h1>Requests</h1>
      <form onSubmit={handleSubmit}>
        <label>
          Brand
          <input value={brand} onChange={(e) => setBrand(e.target.value)} required />
        </label>
        <label>
          Market
          <select value={market} onChange={(e) => setMarket(e.target.value)}>
            <option value="US">US</option>
            <option value="EU">EU</option>
            <option value="Canada">Canada</option>
          </select>
        </label>
        <button type="submit">Submit request</button>
      </form>
      <table>
        <thead>
          <tr><th>ID</th><th>Brand</th><th>Market</th><th>Status</th></tr>
        </thead>
        <tbody>
          {requests.map((r) => (
            <tr key={r.id}>
              <td>{r.id}</td><td>{r.brand}</td><td>{r.market}</td><td>{r.status}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </main>
  );
}
