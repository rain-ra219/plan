import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "AI 自动化控制台",
  description: "AI 自动化后台平台 MVP"
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="zh-CN">
      <body>{children}</body>
    </html>
  );
}
