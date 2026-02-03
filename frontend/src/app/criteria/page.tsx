'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { api } from '@/lib/api';

interface Criterion {
  name: string;
  description: string;
  unit?: string;
  options?: string[];
}

interface Category {
  category: string;
  source: string;
  criteria_count: number;
  created_at: string;
  updated_at: string;
}

export default function CriteriaPage() {
  const [categories, setCategories] = useState<Category[]>([]);
  const [selectedCategory, setSelectedCategory] = useState<string | null>(null);
  const [criteria, setCriteria] = useState<Criterion[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [authToken, setAuthToken] = useState<string>('');
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [editingIndex, setEditingIndex] = useState<number | null>(null);
  const [newCriterion, setNewCriterion] = useState<Criterion>({ name: '', description: '' });
  const [showAddForm, setShowAddForm] = useState(false);
  const [saving, setSaving] = useState(false);

  // Check if auth is required and try to authenticate
  useEffect(() => {
    const storedToken = localStorage.getItem('dashboardAuth');
    if (storedToken) {
      setAuthToken(storedToken);
      loadCategories(storedToken);
    } else {
      // Try without auth (development mode)
      loadCategories('');
    }
  }, []);

  const loadCategories = async (token: string) => {
    try {
      setLoading(true);
      const data = await api.getCategories(token);
      setCategories(data);
      setIsAuthenticated(true);
      setLoading(false);
    } catch (err: unknown) {
      const error = err as Error;
      if (error.message.includes('401')) {
        setIsAuthenticated(false);
        setLoading(false);
      } else {
        setError(error.message);
        setLoading(false);
      }
    }
  };

  const handleLogin = async () => {
    try {
      await api.getCategories(authToken);
      localStorage.setItem('dashboardAuth', authToken);
      setIsAuthenticated(true);
      loadCategories(authToken);
    } catch {
      setError('Invalid password');
    }
  };

  const loadCriteria = async (category: string) => {
    try {
      const data = await api.getCategoryCriteria(category, authToken);
      setCriteria(data.criteria);
      setSelectedCategory(category);
    } catch (err: unknown) {
      const error = err as Error;
      setError(error.message);
    }
  };

  const saveCriteria = async () => {
    if (!selectedCategory) return;
    try {
      setSaving(true);
      await api.updateCategoryCriteria(selectedCategory, criteria, authToken);
      // Reload categories to update counts
      await loadCategories(authToken);
      setSaving(false);
    } catch (err: unknown) {
      const error = err as Error;
      setError(error.message);
      setSaving(false);
    }
  };

  const addCriterion = () => {
    if (!newCriterion.name || !newCriterion.description) return;
    setCriteria([...criteria, { ...newCriterion }]);
    setNewCriterion({ name: '', description: '' });
    setShowAddForm(false);
  };

  const updateCriterion = (index: number, field: keyof Criterion, value: string | string[]) => {
    const updated = [...criteria];
    updated[index] = { ...updated[index], [field]: value };
    setCriteria(updated);
  };

  const deleteCriterion = (index: number) => {
    setCriteria(criteria.filter((_, i) => i !== index));
  };

  const deleteCategory = async (category: string) => {
    if (!confirm(`Delete category "${category}" and all its criteria?`)) return;
    try {
      await api.deleteCategory(category, authToken);
      setCategories(categories.filter(c => c.category !== category));
      if (selectedCategory === category) {
        setSelectedCategory(null);
        setCriteria([]);
      }
    } catch (err: unknown) {
      const error = err as Error;
      setError(error.message);
    }
  };

  // Login screen
  if (!isAuthenticated && !loading) {
    return (
      <div className="min-h-screen bg-gray-900 text-white flex items-center justify-center">
        <div className="bg-gray-800 p-8 rounded-lg max-w-md w-full">
          <h1 className="text-2xl font-bold mb-6">Criteria Management</h1>
          <p className="text-gray-400 mb-4">Enter password to access</p>
          {error && <div className="text-red-400 mb-4">{error}</div>}
          <input
            type="password"
            value={authToken}
            onChange={(e) => setAuthToken(e.target.value)}
            placeholder="Password"
            className="w-full px-4 py-2 bg-gray-700 border border-gray-600 rounded-lg mb-4 focus:outline-none focus:border-indigo-500"
            onKeyDown={(e) => e.key === 'Enter' && handleLogin()}
          />
          <button
            onClick={handleLogin}
            className="w-full px-4 py-2 bg-indigo-600 hover:bg-indigo-700 rounded-lg transition-colors"
          >
            Login
          </button>
        </div>
      </div>
    );
  }

  if (loading) {
    return (
      <div className="min-h-screen bg-gray-900 text-white p-8">
        <div className="max-w-6xl mx-auto">
          <div className="animate-pulse">Loading criteria...</div>
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
            <h1 className="text-2xl font-bold">Criteria Management</h1>
            <p className="text-gray-400 text-sm mt-1">
              {categories.length} product categories with domain criteria
            </p>
          </div>
          <Link
            href="/"
            className="px-4 py-2 bg-indigo-600 hover:bg-indigo-700 rounded-lg text-sm transition-colors"
          >
            Back to Home
          </Link>
        </div>

        {error && (
          <div className="bg-red-900/30 border border-red-700 rounded-lg p-4 mb-6">
            <span className="text-red-400">{error}</span>
            <button onClick={() => setError(null)} className="ml-4 text-red-300 hover:text-white">
              Dismiss
            </button>
          </div>
        )}

        <div className="grid grid-cols-3 gap-6">
          {/* Categories list */}
          <div className="col-span-1 bg-gray-800 rounded-lg p-4">
            <h2 className="text-lg font-semibold mb-4">Categories</h2>
            <div className="space-y-2">
              {categories.map((cat) => (
                <div
                  key={cat.category}
                  className={`p-3 rounded-lg cursor-pointer transition-colors ${
                    selectedCategory === cat.category
                      ? 'bg-indigo-600'
                      : 'bg-gray-700 hover:bg-gray-600'
                  }`}
                  onClick={() => loadCriteria(cat.category)}
                >
                  <div className="flex items-center justify-between">
                    <span className="font-medium">{cat.category}</span>
                    <span className="text-sm text-gray-300">{cat.criteria_count}</span>
                  </div>
                  <div className="text-xs text-gray-400 mt-1">
                    Source: {cat.source}
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Criteria editor */}
          <div className="col-span-2 bg-gray-800 rounded-lg p-4">
            {selectedCategory ? (
              <>
                <div className="flex items-center justify-between mb-4">
                  <h2 className="text-lg font-semibold">
                    Criteria for "{selectedCategory}"
                  </h2>
                  <div className="flex gap-2">
                    <button
                      onClick={() => setShowAddForm(true)}
                      className="px-3 py-1 bg-green-600 hover:bg-green-700 rounded text-sm transition-colors"
                    >
                      + Add Criterion
                    </button>
                    <button
                      onClick={saveCriteria}
                      disabled={saving}
                      className="px-3 py-1 bg-indigo-600 hover:bg-indigo-700 rounded text-sm transition-colors disabled:opacity-50"
                    >
                      {saving ? 'Saving...' : 'Save Changes'}
                    </button>
                    <button
                      onClick={() => deleteCategory(selectedCategory)}
                      className="px-3 py-1 bg-red-600 hover:bg-red-700 rounded text-sm transition-colors"
                    >
                      Delete Category
                    </button>
                  </div>
                </div>

                {/* Add criterion form */}
                {showAddForm && (
                  <div className="bg-gray-700 rounded-lg p-4 mb-4">
                    <h3 className="font-medium mb-3">New Criterion</h3>
                    <div className="grid grid-cols-2 gap-3">
                      <input
                        type="text"
                        placeholder="Name (snake_case)"
                        value={newCriterion.name}
                        onChange={(e) => setNewCriterion({ ...newCriterion, name: e.target.value })}
                        className="px-3 py-2 bg-gray-600 rounded border border-gray-500 focus:outline-none focus:border-indigo-500"
                      />
                      <input
                        type="text"
                        placeholder="Unit (optional)"
                        value={newCriterion.unit || ''}
                        onChange={(e) => setNewCriterion({ ...newCriterion, unit: e.target.value || undefined })}
                        className="px-3 py-2 bg-gray-600 rounded border border-gray-500 focus:outline-none focus:border-indigo-500"
                      />
                      <input
                        type="text"
                        placeholder="Description"
                        value={newCriterion.description}
                        onChange={(e) => setNewCriterion({ ...newCriterion, description: e.target.value })}
                        className="col-span-2 px-3 py-2 bg-gray-600 rounded border border-gray-500 focus:outline-none focus:border-indigo-500"
                      />
                    </div>
                    <div className="flex gap-2 mt-3">
                      <button
                        onClick={addCriterion}
                        className="px-3 py-1 bg-green-600 hover:bg-green-700 rounded text-sm"
                      >
                        Add
                      </button>
                      <button
                        onClick={() => setShowAddForm(false)}
                        className="px-3 py-1 bg-gray-600 hover:bg-gray-500 rounded text-sm"
                      >
                        Cancel
                      </button>
                    </div>
                  </div>
                )}

                {/* Criteria list */}
                <div className="space-y-3">
                  {criteria.map((c, index) => (
                    <div
                      key={index}
                      className="bg-gray-700 rounded-lg p-3"
                    >
                      {editingIndex === index ? (
                        <div className="space-y-2">
                          <div className="grid grid-cols-3 gap-2">
                            <input
                              type="text"
                              value={c.name}
                              onChange={(e) => updateCriterion(index, 'name', e.target.value)}
                              className="px-2 py-1 bg-gray-600 rounded border border-gray-500 text-sm"
                            />
                            <input
                              type="text"
                              value={c.unit || ''}
                              placeholder="Unit"
                              onChange={(e) => updateCriterion(index, 'unit', e.target.value)}
                              className="px-2 py-1 bg-gray-600 rounded border border-gray-500 text-sm"
                            />
                            <input
                              type="text"
                              value={c.options?.join(', ') || ''}
                              placeholder="Options (comma-separated)"
                              onChange={(e) => updateCriterion(index, 'options', e.target.value.split(',').map(s => s.trim()).filter(Boolean))}
                              className="px-2 py-1 bg-gray-600 rounded border border-gray-500 text-sm"
                            />
                          </div>
                          <input
                            type="text"
                            value={c.description}
                            onChange={(e) => updateCriterion(index, 'description', e.target.value)}
                            className="w-full px-2 py-1 bg-gray-600 rounded border border-gray-500 text-sm"
                          />
                          <button
                            onClick={() => setEditingIndex(null)}
                            className="px-2 py-1 bg-indigo-600 rounded text-xs"
                          >
                            Done
                          </button>
                        </div>
                      ) : (
                        <div className="flex items-start justify-between">
                          <div>
                            <div className="flex items-center gap-2">
                              <span className="font-medium text-indigo-400">{c.name}</span>
                              {c.unit && (
                                <span className="text-xs bg-gray-600 px-2 py-0.5 rounded">
                                  {c.unit}
                                </span>
                              )}
                              {c.options && (
                                <span className="text-xs text-gray-400">
                                  [{c.options.join(', ')}]
                                </span>
                              )}
                            </div>
                            <p className="text-sm text-gray-300 mt-1">{c.description}</p>
                          </div>
                          <div className="flex gap-1">
                            <button
                              onClick={() => setEditingIndex(index)}
                              className="px-2 py-1 bg-gray-600 hover:bg-gray-500 rounded text-xs"
                            >
                              Edit
                            </button>
                            <button
                              onClick={() => deleteCriterion(index)}
                              className="px-2 py-1 bg-red-600 hover:bg-red-700 rounded text-xs"
                            >
                              Delete
                            </button>
                          </div>
                        </div>
                      )}
                    </div>
                  ))}

                  {criteria.length === 0 && (
                    <div className="text-center text-gray-400 py-8">
                      No criteria defined. Click "Add Criterion" to add one.
                    </div>
                  )}
                </div>
              </>
            ) : (
              <div className="text-center text-gray-400 py-16">
                Select a category to view and edit its criteria
              </div>
            )}
          </div>
        </div>

        {/* Summary */}
        <div className="mt-6 grid grid-cols-3 gap-4">
          <div className="bg-gray-800 rounded-lg p-4">
            <div className="text-2xl font-bold text-green-400">
              {categories.filter(c => c.source === 'seed').length}
            </div>
            <div className="text-sm text-gray-400">Seeded Categories</div>
          </div>
          <div className="bg-gray-800 rounded-lg p-4">
            <div className="text-2xl font-bold text-cyan-400">
              {categories.filter(c => c.source === 'discovered').length}
            </div>
            <div className="text-sm text-gray-400">Discovered Categories</div>
          </div>
          <div className="bg-gray-800 rounded-lg p-4">
            <div className="text-2xl font-bold text-indigo-400">
              {categories.filter(c => c.source === 'manual').length}
            </div>
            <div className="text-sm text-gray-400">Manual Categories</div>
          </div>
        </div>
      </div>
    </div>
  );
}
