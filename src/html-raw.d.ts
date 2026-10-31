declare module "*.html?raw" {
  const content: string;
  export default content;
}

interface ImportMeta {
  glob(pattern: string, options: { eager: true; query: "?raw"; import: "default" }): Record<string, string>;
}
