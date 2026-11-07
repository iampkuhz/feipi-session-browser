package com.feipi.session.browser.source.common;

import java.io.BufferedInputStream;
import java.io.BufferedOutputStream;
import java.io.BufferedReader;
import java.io.DataInputStream;
import java.io.DataOutputStream;
import java.io.IOException;
import java.io.InputStreamReader;
import java.io.Reader;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.attribute.PosixFilePermissions;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.Set;

/** 在有界词法验证后，以磁盘顺序区间提前替换明确不消费的值；原物理行及字节位置单独保留。 */
public final class JsonlPreprojection implements AutoCloseable {
  private static final int CAPTURE_LIMIT = 128;
  private static final int MAX_DEPTH = 128;
  private final Path directory;
  private final Path projected;
  private final Path positions;

  /**
   * 固定 schema 路径上的投影条件；数组层用 [] 表示，类型必须精确匹配。
   *
   * @param path 固定字段路径
   * @param rootType 顶层事件类型
   * @param payloadType payload 类型，空字符串表示不限
   * @param parentTypes 字段直接父对象允许的类型；空集合表示不限
   */
  public record Rule(String path, String rootType, String payloadType, Set<String> parentTypes) {
    /** 对规则中的父类型集合建立不可变快照。 */
    public Rule {
      parentTypes = Set.copyOf(parentTypes);
    }
  }

  private JsonlPreprojection(Path directory, Path projected, Path positions) {
    this.directory = directory;
    this.projected = projected;
    this.positions = positions;
  }

  static JsonlPreprojection create(Path source, List<Rule> rules, int budget) throws IOException {
    Path directory =
        Files.createTempDirectory(
            "feipi-preprojection-",
            PosixFilePermissions.asFileAttribute(PosixFilePermissions.fromString("rwx------")));
    Path ranges = directory.resolve("ranges");
    Path projected = directory.resolve("projected");
    Path positions = directory.resolve("positions");
    var result = new JsonlPreprojection(directory, projected, positions);
    boolean complete = false;
    try {
      try (var output =
              new DataOutputStream(new BufferedOutputStream(Files.newOutputStream(ranges)));
          Reader input =
              new BufferedReader(
                  new InputStreamReader(
                      Files.newInputStream(source),
                      StandardCharsets.UTF_8
                          .newDecoder()
                          .onMalformedInput(CodingErrorAction.REPORT)
                          .onUnmappableCharacter(CodingErrorAction.REPORT)))) {
        new Scanner(input, output, List.copyOf(rules), Math.max(1, budget / 64)).scan();
      } catch (CharacterCodingException invalid) {
        // 原读取器负责生成其既有全局 INVALID_UTF8 诊断；不使用任何已投影片段。
        return null;
      }
      copy(source, ranges, projected, positions);
      complete = true;
      return result;
    } finally {
      if (!complete) result.close();
    }
  }

  Path projected() {
    return projected;
  }

  DataInputStream positions() throws IOException {
    return new DataInputStream(new BufferedInputStream(Files.newInputStream(positions)));
  }

  private static void copy(Path source, Path ranges, Path target, Path positions)
      throws IOException {
    try (var input = new BufferedInputStream(Files.newInputStream(source));
        var intervals = new DataInputStream(new BufferedInputStream(Files.newInputStream(ranges)));
        var output = new BufferedOutputStream(Files.newOutputStream(target));
        var lines =
            new DataOutputStream(new BufferedOutputStream(Files.newOutputStream(positions)))) {
      long start = intervals.available() > 0 ? intervals.readLong() : Long.MAX_VALUE;
      long end = start == Long.MAX_VALUE ? start : intervals.readLong();
      long offset = 0;
      long lineBytes = 0;
      boolean carriage = false;
      boolean nonEmpty = false;
      int codePoint = 0;
      int remainingUtf8 = 0;
      int value;
      while ((value = input.read()) != -1) {
        if (offset == end) {
          start = intervals.available() > 0 ? intervals.readLong() : Long.MAX_VALUE;
          end = start == Long.MAX_VALUE ? start : intervals.readLong();
        }
        if (offset == start) output.write("null".getBytes(StandardCharsets.US_ASCII));
        if (offset < start || value == '\n' || value == '\r') output.write(value);
        if (carriage && value != '\n') {
          lines.writeLong(lineBytes);
          lines.writeBoolean(nonEmpty);
          nonEmpty = false;
          lineBytes = 0;
        }
        if (value < 128) {
          if (!Character.isWhitespace(value)) nonEmpty = true;
        } else if (remainingUtf8 == 0) {
          remainingUtf8 = value < 224 ? 1 : value < 240 ? 2 : 3;
          codePoint = value & (remainingUtf8 == 1 ? 31 : remainingUtf8 == 2 ? 15 : 7);
        } else {
          codePoint = (codePoint << 6) | (value & 63);
          remainingUtf8--;
          if (remainingUtf8 == 0
              && !(offset == 2 && codePoint == 0xfeff)
              && !Character.isWhitespace(codePoint)) nonEmpty = true;
        }
        lineBytes++;
        if (value == '\n') {
          lines.writeLong(lineBytes);
          lines.writeBoolean(nonEmpty);
          nonEmpty = false;
          lineBytes = 0;
        }
        carriage = value == '\r';
        offset++;
      }
      if (lineBytes > 0) {
        lines.writeLong(lineBytes);
        lines.writeBoolean(nonEmpty);
      }
    }
  }

  @Override
  public void close() throws IOException {
    try {
      Files.deleteIfExists(projected);
      Files.deleteIfExists(positions);
      Files.deleteIfExists(directory.resolve("ranges"));
    } finally {
      Files.deleteIfExists(directory);
    }
  }

  /** 已完整验证的候选值区间，类型身份在父对象结束后确认。 */
  private static final class Candidate {
    private final long start;
    private final long end;
    private final Rule rule;
    private String parentType = "";

    private Candidate(long start, long end, Rule rule) {
      this.start = start;
      this.end = end;
      this.rule = rule;
    }
  }

  /** 保守放弃当前记录投影，不替代原 reader 的错误诊断。 */
  private static final class Invalid extends Exception {
    private static final long serialVersionUID = 1L;
  }

  /** 仅捕获短字段名和类型；任意大字符串均逐字符验证，不构建 TextBuffer。 */
  private static final class Scanner {
    private final Reader input;
    private final DataOutputStream output;
    private final List<Rule> rules;
    private final int candidateLimit;
    private final List<Candidate> candidates = new ArrayList<>();
    private final List<String> path = new ArrayList<>();
    private int next = -2;
    private long offset;
    private boolean highSurrogate;
    private String rootType = "";
    private String payloadType = "";

    private Scanner(Reader input, DataOutputStream output, List<Rule> rules, int candidateLimit) {
      this.input = input;
      this.output = output;
      this.rules = rules;
      this.candidateLimit = candidateLimit;
    }

    private void scan() throws IOException {
      if (peek() == '\ufeff') take();
      while (true) {
        whitespace();
        if (peek() == -1) return;
        candidates.clear();
        path.clear();
        rootType = payloadType = "";
        try {
          value(0, false);
          candidates.sort(Comparator.comparingLong(candidate -> candidate.start));
          long previousEnd = -1;
          for (Candidate candidate : candidates) {
            Rule rule = candidate.rule;
            if (candidate.start >= previousEnd
                && rule.rootType().equals(rootType)
                && (rule.payloadType().isEmpty() || rule.payloadType().equals(payloadType))
                && (rule.parentTypes().isEmpty()
                    || rule.parentTypes().contains(candidate.parentType))) {
              output.writeLong(candidate.start);
              output.writeLong(candidate.end);
              previousEnd = candidate.end;
            }
          }
        } catch (Invalid invalid) {
          // 未完整验证的记录不提交任何区间；原始内容和错误交给既有 reader。
          while (peek() != -1 && peek() != '\n' && peek() != '\r') take();
        }
      }
    }

    private int peek() throws IOException {
      if (next == -2) next = input.read();
      return next;
    }

    private int take() throws IOException {
      int value = peek();
      next = -2;
      if (value != -1) {
        char ch = (char) value;
        offset +=
            Character.isHighSurrogate(ch)
                ? 4
                : Character.isLowSurrogate(ch) && highSurrogate
                    ? 0
                    : ch <= 127 ? 1 : ch <= 2047 ? 2 : 3;
        highSurrogate = Character.isHighSurrogate(ch);
      }
      return value;
    }

    private void whitespace() throws IOException {
      while (peek() == ' ' || peek() == '\t' || peek() == '\n' || peek() == '\r') take();
    }

    private void expect(int expected) throws IOException, Invalid {
      if (take() != expected) throw new Invalid();
    }

    private String string(boolean capture) throws IOException, Invalid {
      expect('"');
      StringBuilder retained = new StringBuilder();
      boolean tooLong = false;
      int value;
      while ((value = take()) != '"') {
        if (value < 32) throw new Invalid();
        if (value == '\\') {
          int escape = take();
          if (escape == 'u') {
            value = 0;
            for (int index = 0; index < 4; index++) {
              int rawDigit = take();
              int digit = rawDigit < 128 ? Character.digit(rawDigit, 16) : -1;
              if (digit < 0) throw new Invalid();
              value = value * 16 + digit;
            }
          } else {
            if (escape < 0 || "\"\\/bfnrt".indexOf(escape) < 0) throw new Invalid();
            value =
                switch (escape) {
                  case 'b' -> '\b';
                  case 'f' -> '\f';
                  case 'n' -> '\n';
                  case 'r' -> '\r';
                  case 't' -> '\t';
                  default -> escape;
                };
          }
        }
        if (capture) {
          if (retained.length() < CAPTURE_LIMIT) retained.append((char) value);
          else tooLong = true;
        }
      }
      return tooLong ? "" : retained.toString();
    }

    private String value(int depth, boolean capture) throws IOException, Invalid {
      if (depth > MAX_DEPTH) throw new Invalid();
      whitespace();
      int value = peek();
      if (value == '{') return object(depth);
      if (value == '[') {
        take();
        whitespace();
        if (peek() == ']') {
          take();
          return "";
        }
        while (true) {
          path.add("[]");
          value(depth + 1, false);
          path.removeLast();
          whitespace();
          int separator = take();
          if (separator == ']') return "";
          if (separator != ',') throw new Invalid();
        }
      }
      if (value == '"') return string(capture);
      StringBuilder token = new StringBuilder();
      while (peek() != -1 && ",]} \r\n\t".indexOf(peek()) < 0) {
        if (token.length() == CAPTURE_LIMIT) throw new Invalid();
        token.append((char) take());
      }
      if (!Set.of("true", "false", "null").contains(token.toString())
          && !token.toString().matches("-?(?:0|[1-9][0-9]*)(?:\\.[0-9]+)?(?:[eE][+-]?[0-9]+)?"))
        throw new Invalid();
      return "";
    }

    private String object(int depth) throws IOException, Invalid {
      expect('{');
      String objectType = "";
      boolean typeSeen = false;
      boolean payloadSeen = false;
      List<Candidate> direct = new ArrayList<>();
      whitespace();
      if (peek() == '}') {
        take();
        return "";
      }
      while (true) {
        whitespace();
        String key = string(true);
        if (key.equals("type")) {
          if (typeSeen) throw new Invalid();
          typeSeen = true;
        }
        if (path.isEmpty() && key.equals("payload")) {
          if (payloadSeen) throw new Invalid();
          payloadSeen = true;
        }
        whitespace();
        expect(':');
        whitespace();
        path.add(key.equals("[]") || key.contains(".") ? "<unmatched-key>" : key);
        long start = offset;
        String captured = value(depth + 1, key.equals("type"));
        String fieldPath = String.join(".", path);
        while (fieldPath.contains(".[].[]")) fieldPath = fieldPath.replace(".[].[]", ".[]");
        for (Rule rule : rules) {
          if (rule.path().equals(fieldPath)) {
            if (candidates.size() >= candidateLimit) throw new Invalid();
            Candidate candidate = new Candidate(start, offset, rule);
            candidates.add(candidate);
            direct.add(candidate);
          }
        }
        path.removeLast();
        if (key.equals("type")) objectType = captured;
        whitespace();
        int separator = take();
        if (separator == '}') break;
        if (separator != ',') throw new Invalid();
      }
      if (path.isEmpty()) rootType = objectType;
      else if (path.size() == 1 && path.getFirst().equals("payload")) payloadType = objectType;
      for (Candidate candidate : direct) candidate.parentType = objectType;
      return "";
    }
  }
}
