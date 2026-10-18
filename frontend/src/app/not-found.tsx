import Link from "next/link";

export default function NotFound() {
  return (
    <div className="flex flex-col items-center justify-center min-h-screen text-center p-4 bg-m3-surface text-m3-on-surface">
      <h2 className="text-xl font-bold text-white mb-2">404 - Page Not Found</h2>
      <Link href="/" className="text-xs text-m3-primary hover:underline">
        Return Home
      </Link>
    </div>
  );
}
