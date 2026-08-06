let counter = 0;

export function id(prefix: string): string {
  counter += 1;
  return `${prefix}_${counter.toString(36).padStart(4, "0")}`;
}

export function resetIdCounter(): void {
  counter = 0;
}
