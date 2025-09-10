import { clsx, type ClassValue } from "clsx"
import { twMerge } from "tailwind-merge"

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

export function generateSessionTitle(text: string): string {
  const words = text.match(/\w+/g) || [];
  if (words.length === 0) return 'New Chat';
  const count = Math.min(4, words.length);
  const titleWords = words.slice(0, count < 3 ? words.length : count);
  return titleWords.join(' ').replace(/(^|\s)\S/g, s => s.toUpperCase());
}
