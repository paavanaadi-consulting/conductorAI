"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  FolderPlus,
  LayoutDashboard,
  GitBranch,
} from "lucide-react";
import { cn } from "@/lib/utils";

const NAV = [
  { href: "/projects/new", label: "New Project", icon: FolderPlus },
  { href: "/projects", label: "Projects", icon: LayoutDashboard },
];

export function Sidebar() {
  const pathname = usePathname();

  return (
    <aside className="w-60 border-r bg-background flex flex-col">
      <div className="p-6 border-b">
        <Link href="/" className="flex items-center gap-2">
          <GitBranch className="h-6 w-6 text-primary" />
          <span className="text-lg font-bold">ConductorAI</span>
        </Link>
      </div>
      <nav className="flex-1 p-4 space-y-1">
        {NAV.map(({ href, label, icon: Icon }) => (
          <Link
            key={href}
            href={href}
            className={cn(
              "flex items-center gap-3 px-3 py-2 rounded-md text-sm transition-colors",
              pathname === href || (href !== "/" && pathname.startsWith(href))
                ? "bg-primary/10 text-primary font-medium"
                : "text-muted-foreground hover:bg-muted"
            )}
          >
            <Icon className="h-4 w-4" />
            {label}
          </Link>
        ))}
      </nav>
      <div className="p-4 border-t text-xs text-muted-foreground">
        ConductorAI v0.1.0
      </div>
    </aside>
  );
}
