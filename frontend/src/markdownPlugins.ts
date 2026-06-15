import remarkGfm from "remark-gfm";
import remarkMath from "remark-math";
import rehypeKatex from "rehype-katex";
import type { PluggableList } from "unified";

/** Shared markdown pipeline: GFM + $inline$ / $$display$$ math → KaTeX. */
export const markdownRemarkPlugins: PluggableList = [remarkGfm, remarkMath];

export const markdownRehypePlugins: PluggableList = [
  [
    rehypeKatex,
    {
      throwOnError: false,
      strict: false,
    },
  ],
];
