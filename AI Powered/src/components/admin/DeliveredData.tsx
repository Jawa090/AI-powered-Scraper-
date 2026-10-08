import React, { useEffect, useState } from 'react';
import { apiService } from '../../services/api.service';

type Row = { id: string; company?: string; companyName?: string; name?: string; category?: string;
  industry?: string; title?: string; city?: string; state?: string; email?: string; phone?: string; sourceCode?: string; sourceUrl?: string };
type Delivery = { queryId: string; request?: string; servedAt: string; records: Row[]; snapshotAvailable: boolean;
  requestFulfilled?: boolean; deliveryKind?: string; matchingRecordsDelivered?: number; requestedRecords?: number;
  collectionCancelled?: boolean; timedOut?: boolean;
  understoodRequest?: Record<string, any> };
type Group = { userId: string; heading: string; total: number; deliveries: Delivery[] };

export const DeliveredData: React.FC = () => {
  const [groups, setGroups] = useState<Group[]>([]);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const load = async () => {
    setLoading(true); setError('');
    try {
      const response = await apiService.fetchWithAuth(`${apiService.baseUrl}/api/admin/deliveries?page=${page}&page_size=10`);
      if (!response.ok) throw new Error(`Could not load deliveries (${response.status})`);
      setGroups((await response.json()).groups);
    } catch (err) { setError(err instanceof Error ? err.message : 'Could not load deliveries'); }
    finally { setLoading(false); }
  };
  useEffect(() => { void load(); }, [page]);
  return <section className="space-y-4" aria-label="Delivered data by user">
    <div className="flex justify-between items-center"><div>
      <h2 className="text-lg font-bold text-gray-900 dark:text-golden-100">Data delivered to users</h2>
      <p className="text-sm text-gray-600 dark:text-gray-300">Saved values from each delivery, grouped by account email.</p>
    </div><div className="flex gap-2"><button className="px-3 py-2 border rounded dark:text-gray-100" onClick={async () => {
      try { await apiService.downloadAuthenticated(`${apiService.baseUrl}/api/admin/deliveries/export.csv`, 'delivered_data.csv'); }
      catch (err) { setError(err instanceof Error ? err.message : 'Export failed'); }
    }}>Export delivered data</button><button className="px-3 py-2 border rounded dark:text-gray-100" onClick={() => void load()} disabled={loading}>Refresh</button></div></div>
    {error && <p role="alert" className="text-red-600">{error}</p>}
    {loading && <p className="dark:text-gray-100">Loading deliveries…</p>}
    {!loading && groups.length === 0 && <p>No delivered data yet.</p>}
    {groups.map(group => <article key={group.userId} className="border border-gray-200 dark:border-gray-700 rounded-xl bg-white dark:bg-gray-900 overflow-hidden">
      <h3 className="px-4 py-3 text-lg font-bold text-gray-900 dark:text-golden-100 border-b dark:border-gray-700">{group.heading}</h3>
      {group.deliveries.length === 0 ? <p className="p-4 text-gray-600 dark:text-gray-300">{group.total ? 'No deliveries on this page.' : 'No data delivered yet.'}</p> :
        group.deliveries.map(delivery => <div key={delivery.queryId} className="p-4 border-b dark:border-gray-700">
          <p className="text-sm mb-2 text-gray-700 dark:text-gray-200">{delivery.request} · {new Date(delivery.servedAt).toLocaleString()} · {delivery.records.length} records · Request {delivery.queryId}</p>
          {delivery.understoodRequest && Object.keys(delivery.understoodRequest).length > 0 && <details className="mb-2 text-sm text-gray-700 dark:text-gray-200">
            <summary>What the model understood</summary>
            <dl className="grid grid-cols-2 gap-1 mt-2">{Object.entries(delivery.understoodRequest).filter(([, value]) => value !== null && value !== undefined).map(([key, value]) =>
              <React.Fragment key={key}><dt>{key.replace(/_/g, ' ')}</dt><dd>{String(value)}</dd></React.Fragment>)}</dl>
          </details>}
          {delivery.requestFulfilled === false && <p role="status" className="mb-3 p-3 rounded border border-amber-400 text-amber-800 dark:text-amber-200">
            {delivery.collectionCancelled ? 'Chat cleared — request cancelled' : 'Request not fulfilled'} — {delivery.matchingRecordsDelivered ?? 0} of {delivery.requestedRecords ?? 0} required matches found.
            {' '}This is the recovered data ({delivery.records.length} records); it may differ from the requested requirements.
          </p>}
          {delivery.timedOut && <p className="mb-2 text-amber-800 dark:text-amber-200">Scraper stopped after five minutes without records.</p>}
          {delivery.requestFulfilled === true && <p className="mb-2 text-sm text-green-700 dark:text-green-300">Request fulfilled — showing only the requested matching records.</p>}
          {!delivery.snapshotAvailable && <p className="text-sm text-amber-700 dark:text-amber-300">Legacy delivery: historical field values were not captured.</p>}
          <div className="overflow-x-auto"><table className="w-full text-sm text-left text-gray-800 dark:text-gray-100">
            <thead><tr>{['Company / title', 'Category', 'City', 'State', 'Email', 'Phone', 'Source'].map(label => <th key={label} className="p-2 border-b dark:border-gray-700">{label}</th>)}</tr></thead>
            <tbody>{delivery.records.map((row, index) => <tr key={`${row.id}-${index}`}>
              <td className="p-2">{row.company || row.companyName || row.title || row.name || '—'}</td>
              <td className="p-2">{row.category || row.industry || '—'}</td><td className="p-2">{row.city || '—'}</td>
              <td className="p-2">{row.state || '—'}</td><td className="p-2">{row.email || '—'}</td><td className="p-2">{row.phone || '—'}</td>
              <td className="p-2">{row.sourceUrl ? <a href={row.sourceUrl} target="_blank" rel="noreferrer" className="underline">{row.sourceCode || 'Source'}</a> : row.sourceCode || '—'}</td>
            </tr>)}</tbody>
          </table></div>
          <details className="mt-3 text-sm text-gray-700 dark:text-gray-200">
            <summary>Full saved delivery data</summary>
            <pre className="mt-2 max-h-96 overflow-auto whitespace-pre-wrap break-words text-xs">{JSON.stringify(delivery.records, null, 2)}</pre>
          </details>
        </div>)}
      <p className="px-4 py-2 text-xs text-gray-600 dark:text-gray-300">{group.total} deliveries</p>
    </article>)}
    <div className="flex gap-3 items-center dark:text-gray-100">
      <button className="border rounded px-3 py-1 disabled:opacity-40" disabled={page === 1 || loading} onClick={() => setPage(page - 1)}>Previous</button>
      <span>Page {page}</span><button className="border rounded px-3 py-1 disabled:opacity-40" disabled={loading || groups.every(g => g.total <= page * 10)} onClick={() => setPage(page + 1)}>Next</button>
    </div>
  </section>;
};
