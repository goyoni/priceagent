'use client';

export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <html>
      <body className="min-h-screen bg-gray-900 text-white flex items-center justify-center p-8">
        <div className="text-center">
          <h2 className="text-2xl font-bold mb-4">Something went wrong!</h2>
          <p className="text-gray-400 mb-6">{error.message}</p>
          <button
            onClick={() => reset()}
            className="px-4 py-2 bg-indigo-600 hover:bg-indigo-700 rounded-lg transition-colors"
          >
            Try again
          </button>
        </div>
      </body>
    </html>
  );
}
