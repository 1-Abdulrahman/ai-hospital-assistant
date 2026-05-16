import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

// Combines class names and resolves Tailwind conflicts into a single string.
export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}
