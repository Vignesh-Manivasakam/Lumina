import './globals.css';
import React from 'react';

export const metadata = {
  title: 'Lumina — Enterprise Document Intelligence',
  description:
    'Deep research over your documents with verified, real-time intelligence.',
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className="antialiased min-h-screen flex flex-col bg-transparent text-slate-900 dark:text-slate-100">
        {children}
      </body>
    </html>
  );
}
