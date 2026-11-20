import "./globals.css";
import type { ReactNode } from "react";

export const metadata = { title: "Nexus · лаборатория SOLUSDT", description: "Локальная проверка торговых правил" };
export default function Layout({ children }: { children: ReactNode }) {
  return <html lang="ru"><body>{children}</body></html>;
}
