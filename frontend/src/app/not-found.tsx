import Link from 'next/link';

export default function NotFound() {
  return (
    <div className="min-h-screen bg-gray-900 text-white flex items-center justify-center p-8">
      <div className="text-center">
        <h2 className="text-4xl font-bold mb-4">404</h2>
        <p className="text-gray-400 mb-6">Page not found</p>
        <Link
          href="/"
          className="px-4 py-2 bg-indigo-600 hover:bg-indigo-700 rounded-lg transition-colors inline-block"
        >
          Go home
        </Link>
      </div>
    </div>
  );
}
