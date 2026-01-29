'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { api } from '@/lib/api';

interface Seller {
  id: number;
  seller_name: string;
  domain: string;
  phone_number?: string;
  whatsapp_number?: string;
  website_url?: string;
  rating?: number;
}

export default function SellersPage() {
  const [sellers, setSellers] = useState<Seller[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState('');

  useEffect(() => {
    api.getSellers()
      .then((data) => {
        setSellers(data);
        setLoading(false);
      })
      .catch((err) => {
        setError(err.message);
        setLoading(false);
      });
  }, []);

  const filteredSellers = sellers.filter((s) => {
    const searchLower = search.toLowerCase();
    return (
      s.seller_name.toLowerCase().includes(searchLower) ||
      s.domain.toLowerCase().includes(searchLower) ||
      s.whatsapp_number?.includes(search) ||
      s.phone_number?.includes(search)
    );
  });

  if (loading) {
    return (
      <div className="min-h-screen bg-gray-900 text-white p-8">
        <div className="max-w-6xl mx-auto">
          <div className="animate-pulse">Loading sellers...</div>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="min-h-screen bg-gray-900 text-white p-8">
        <div className="max-w-6xl mx-auto">
          <div className="text-red-400">Error: {error}</div>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-900 text-white p-8">
      <div className="max-w-6xl mx-auto">
        {/* Header */}
        <div className="flex items-center justify-between mb-6">
          <div>
            <h1 className="text-2xl font-bold">Sellers Database</h1>
            <p className="text-gray-400 text-sm mt-1">
              {sellers.length} sellers with contact information
            </p>
          </div>
          <Link
            href="/"
            className="px-4 py-2 bg-indigo-600 hover:bg-indigo-700 rounded-lg text-sm transition-colors"
          >
            Back to Dashboard
          </Link>
        </div>

        {/* Search */}
        <div className="mb-6">
          <input
            type="text"
            placeholder="Search by name, domain, or phone..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full max-w-md px-4 py-2 bg-gray-800 border border-gray-700 rounded-lg focus:outline-none focus:border-indigo-500"
          />
        </div>

        {/* Table */}
        <div className="bg-gray-800 rounded-lg overflow-hidden">
          <table className="w-full">
            <thead className="bg-gray-700">
              <tr>
                <th className="px-4 py-3 text-left text-sm font-medium text-gray-300">ID</th>
                <th className="px-4 py-3 text-left text-sm font-medium text-gray-300">Name</th>
                <th className="px-4 py-3 text-left text-sm font-medium text-gray-300">Domain</th>
                <th className="px-4 py-3 text-left text-sm font-medium text-gray-300">WhatsApp</th>
                <th className="px-4 py-3 text-left text-sm font-medium text-gray-300">Phone</th>
                <th className="px-4 py-3 text-left text-sm font-medium text-gray-300">Website</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-700">
              {filteredSellers.map((seller) => (
                <tr key={seller.id} className="hover:bg-gray-750">
                  <td className="px-4 py-3 text-sm text-gray-400">{seller.id}</td>
                  <td className="px-4 py-3 text-sm font-medium">{seller.seller_name}</td>
                  <td className="px-4 py-3 text-sm text-indigo-400">{seller.domain}</td>
                  <td className="px-4 py-3 text-sm">
                    {seller.whatsapp_number ? (
                      <a
                        href={`https://wa.me/${seller.whatsapp_number.replace(/[^0-9]/g, '')}`}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-green-400 hover:text-green-300 hover:underline"
                      >
                        {seller.whatsapp_number}
                      </a>
                    ) : (
                      <span className="text-gray-500">-</span>
                    )}
                  </td>
                  <td className="px-4 py-3 text-sm">
                    {seller.phone_number ? (
                      <a
                        href={`tel:${seller.phone_number}`}
                        className="text-cyan-400 hover:text-cyan-300 hover:underline"
                      >
                        {seller.phone_number}
                      </a>
                    ) : (
                      <span className="text-gray-500">-</span>
                    )}
                  </td>
                  <td className="px-4 py-3 text-sm">
                    {seller.website_url ? (
                      <a
                        href={seller.website_url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-blue-400 hover:text-blue-300 hover:underline truncate block max-w-xs"
                        title={seller.website_url}
                      >
                        {seller.domain}
                      </a>
                    ) : (
                      <span className="text-gray-500">-</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>

          {filteredSellers.length === 0 && (
            <div className="px-4 py-8 text-center text-gray-400">
              No sellers found matching "{search}"
            </div>
          )}
        </div>

        {/* Summary */}
        <div className="mt-6 grid grid-cols-3 gap-4">
          <div className="bg-gray-800 rounded-lg p-4">
            <div className="text-2xl font-bold text-green-400">
              {sellers.filter(s => s.whatsapp_number).length}
            </div>
            <div className="text-sm text-gray-400">With WhatsApp</div>
          </div>
          <div className="bg-gray-800 rounded-lg p-4">
            <div className="text-2xl font-bold text-cyan-400">
              {sellers.filter(s => s.phone_number).length}
            </div>
            <div className="text-sm text-gray-400">With Phone</div>
          </div>
          <div className="bg-gray-800 rounded-lg p-4">
            <div className="text-2xl font-bold text-indigo-400">
              {sellers.filter(s => !s.whatsapp_number && !s.phone_number).length}
            </div>
            <div className="text-sm text-gray-400">No Contact</div>
          </div>
        </div>
      </div>
    </div>
  );
}
