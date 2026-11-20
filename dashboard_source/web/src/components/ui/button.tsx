import type { ButtonHTMLAttributes } from "react";
import { cn } from "@/lib/utils";

export function Button({ className, variant = "default", ...props }: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: "default" | "outline" }) {
  return <button className={cn("inline-flex min-h-11 cursor-pointer items-center justify-center rounded-lg px-4 font-semibold focus-visible:outline-2 disabled:cursor-default disabled:opacity-50",variant==="outline"?"border border-slate-300 bg-white text-slate-800":"bg-blue-700 text-white hover:bg-blue-800",className)} {...props} />;
}
