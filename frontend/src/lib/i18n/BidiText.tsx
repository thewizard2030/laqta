import React from "react";
import { detectTextDirection, bidiContainerStyle } from "./bidi";

interface BidiTextProps {
  text: string | null | undefined;
  className?: string;
  as?: "p" | "span" | "div";
  title?: string;
}

/**
 * Direction-aware text renderer for transcript excerpts and captions.
 * Arabic/RTL scripts get dir="rtl"; English/LTR gets dir="ltr";
 * mixed-direction text keeps the first-strong-character base direction and
 * lets the browser's bidi algorithm place embedded runs. The exact rule is
 * implemented and tested in bidi.ts.
 */
export const BidiText: React.FC<BidiTextProps> = ({ text, className, as = "p", title }) => {
  const dir = detectTextDirection(text);
  const style = bidiContainerStyle(text);
  const Tag = as;
  return (
    <Tag title={title} dir={dir} style={style} className={className}>
      {text}
    </Tag>
  );
};
