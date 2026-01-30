/**
 * CountrySelector component for manual country override.
 */

'use client';

interface CountrySelectorProps {
  value: string;
  onChange: (country: string) => void;
  compact?: boolean;
}

const SUPPORTED_COUNTRIES = [
  { code: 'IL', name: 'Israel', flag: '🇮🇱' },
  { code: 'US', name: 'United States', flag: '🇺🇸' },
  { code: 'UK', name: 'United Kingdom', flag: '🇬🇧' },
  { code: 'DE', name: 'Germany', flag: '🇩🇪' },
  { code: 'FR', name: 'France', flag: '🇫🇷' },
];

export function CountrySelector({ value, onChange, compact = false }: CountrySelectorProps) {
  const selectedCountry = SUPPORTED_COUNTRIES.find(c => c.code === value) || SUPPORTED_COUNTRIES[0];

  if (compact) {
    return (
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="bg-slate-800 border border-slate-600 text-slate-300 text-sm rounded-lg
                 px-2 py-1 outline-none focus:border-cyan-500 cursor-pointer"
      >
        {SUPPORTED_COUNTRIES.map((country) => (
          <option key={country.code} value={country.code}>
            {country.flag} {country.code}
          </option>
        ))}
      </select>
    );
  }

  return (
    <div className="flex items-center gap-2">
      <span className="text-sm text-slate-500">Region:</span>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="bg-slate-800 border border-slate-600 text-slate-300 text-sm rounded-lg
                 px-3 py-1.5 outline-none focus:border-cyan-500 cursor-pointer"
      >
        {SUPPORTED_COUNTRIES.map((country) => (
          <option key={country.code} value={country.code}>
            {country.flag} {country.name}
          </option>
        ))}
      </select>
    </div>
  );
}
