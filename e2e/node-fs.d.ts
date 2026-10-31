declare module "node:fs" {
  export function readFileSync(path: string, encoding: "utf8"): string;
  export function mkdirSync(path: string, options: { recursive: boolean }): void;
  export function copyFileSync(from: string, to: string): void;
}
