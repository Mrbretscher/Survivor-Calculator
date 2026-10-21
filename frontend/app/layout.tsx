import type { Metadata } from "next";
import SiteNavigation from "./site-navigation";
import "./styles.css";

export const metadata: Metadata = {
  title: "Survivor Calculator",
  description: "For-fun Survivor current-season prediction board"
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>
        <SiteNavigation />
        {children}
      </body>
    </html>
  );
}

