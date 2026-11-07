package com.feipi.session.browser.source.common;

import java.io.IOException;
import java.io.Reader;

/** 按固定字符块读取物理行；超限后仍解码并排空，不积累整行。 */
final class BoundedPhysicalLineReader implements AutoCloseable {
  private final Reader reader;
  private final char[] chunk = new char[8192];
  private int position;
  private int available;
  private int pushed = -1;
  private boolean firstCharacter = true;

  BoundedPhysicalLineReader(Reader reader) {
    this.reader = reader;
  }

  Line next(int budget, int previewLimit) throws IOException {
    StringBuilder retained = new StringBuilder();
    StringBuilder preview = new StringBuilder();
    long effectiveLength = 0;
    long physicalLength = 0;
    long bytes = 0;
    int lastNonWhitespace = 0;
    int curlyDelta = 0;
    int squareDelta = 0;
    boolean overflow = false;
    boolean seen = false;
    boolean previousHighSurrogate = false;
    int value;
    while ((value = nextCharacter()) != -1) {
      seen = true;
      char ch = (char) value;
      if (ch == '\r' || ch == '\n') {
        firstCharacter = false;
        bytes++;
        if (ch == '\r') {
          int following = nextCharacter();
          if (following == '\n') bytes++;
          else pushed = following;
        }
        break;
      }
      bytes +=
          Character.isHighSurrogate(ch)
              ? 4
              : Character.isLowSurrogate(ch) && previousHighSurrogate
                  ? 0
                  : ch <= 0x7f ? 1 : ch <= 0x7ff ? 2 : 3;
      previousHighSurrogate = Character.isHighSurrogate(ch);
      if (firstCharacter && ch == JsonlConstants.BOM) {
        firstCharacter = false;
        continue;
      }
      firstCharacter = false;
      if (ch == '{') curlyDelta++;
      else if (ch == '}') curlyDelta--;
      else if (ch == '[') squareDelta++;
      else if (ch == ']') squareDelta--;
      physicalLength++;
      if (preview.length() < previewLimit) preview.append(ch);
      if (retained.length() < Math.max(0, budget)) retained.append(ch);
      if (!Character.isWhitespace(ch)) {
        effectiveLength = physicalLength;
        if (effectiveLength > budget) overflow = true;
        else lastNonWhitespace = retained.length();
      }
    }
    if (!seen) return null;
    if (overflow) return new Line(preview.toString(), true, bytes, curlyDelta, squareDelta);
    retained.setLength(lastNonWhitespace);
    return new Line(retained.toString(), false, bytes, curlyDelta, squareDelta);
  }

  private int nextCharacter() throws IOException {
    if (pushed != -1) {
      int result = pushed;
      pushed = -1;
      return result;
    }
    if (available == -1) return -1;
    if (position == available) {
      do {
        available = reader.read(chunk);
      } while (available == 0);
      position = 0;
      if (available == -1) return -1;
    }
    return chunk[position++];
  }

  @Override
  public void close() throws IOException {
    reader.close();
  }

  /**
   * 保留有界正文或预览，以及完整物理行的位置和跳过态括号变化。
   *
   * @param text 去掉尾空白的合法行，或超限行的有界预览
   * @param overflow 非尾空白内容是否超过剩余记录预算
   * @param bytesConsumed 含原行终止符和首 BOM 的实际 UTF-8 字节数
   * @param curlyDelta 原物理行花括号净变化，用于既有停止状态
   * @param squareDelta 原物理行方括号净变化，用于既有停止状态
   */
  record Line(
      /* 去掉尾空白的合法行，或超限行的有界预览。 */ String text,
      /* 非尾空白内容是否超过剩余记录预算。 */ boolean overflow,
      /* 含原行终止符和首 BOM 的实际 UTF-8 字节数。 */ long bytesConsumed,
      /* 原物理行花括号净变化，用于既有停止状态。 */ int curlyDelta,
      /* 原物理行方括号净变化，用于既有停止状态。 */ int squareDelta) {}
}
