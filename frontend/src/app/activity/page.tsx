"use client";
import * as React from "react";
import { useLeagueData } from "@/lib/league-context";
import { Badge, Card, Empty, ErrorBox, PageHeader, Segmented, Spinner } from "@/components/ui";
import { NeedLeague } from "@/components/shell";

 
export default function ActivityPage() {
  return <NeedLeague><Inner /></NeedLeague>;
}

const TONE: Record<string, any> = { add: "good", drop: "bad", trade: "blue", trade_offer: "amber", matchup: "teal", draft: "teal", league: "neutral" };

function Inner() {
  const [tab, setTab] = React.useState<"feed" | "tx">("feed");
  const feed = useLeagueData<any[]>("/activity?limit=100");
  const tx = useLeagueData<any[]>("/transactions");
  const cur = tab === "feed" ? feed : tx;
  return (
    <>
      <PageHeader title="League Activity" sub="Everything that happened in your league" action={<Segmented label="View" value={tab} onChange={setTab} options={[{ value: "feed", label: "Activity feed" }, { value: "tx", label: "Transactions" }]} />} />
      {cur.error ? <ErrorBox message={cur.error} onRetry={cur.reload} /> : cur.loading && !cur.data ? <Spinner /> : (
        <Card pad={false}>
          {!cur.data?.length && <Empty>Nothing here yet.</Empty>}
          {tab === "feed" ? (
            <ul className="divide-y divide-line">{feed.data?.map((a) => <li key={a.id} className="flex items-center gap-3 px-4 py-2.5 text-sm"><Badge tone={TONE[a.kind] ?? "neutral"} className="w-20 justify-center">{a.kind.replace("_", " ")}</Badge><span className="flex-1">{a.message}</span><span className="num text-xs text-ink3">day {a.day}</span></li>)}</ul>
          ) : (
            <table className="w-full text-sm"><tbody>{tx.data?.map((t) => (
              <tr key={t.id} className="border-b border-line/60"><td className="px-4 py-2 text-ink3 num">D{t.day}</td><td className="p-2"><Badge tone={t.kind === "add" || t.kind === "trade_in" ? "good" : "bad"}>{t.kind.replace("_", " ")}</Badge></td>
                <td className="p-2">{t.team}</td><td className="p-2 font-medium">{t.player} <span className="text-[11px] text-ink3">{t.positions.replace(",", "/")}</span></td><td className="p-2 text-ink3">{t.related_team ? `↔ ${t.related_team}` : ""}</td></tr>))}</tbody></table>
          )}
        </Card>
      )}
    </>
  );
}
