package com.feipi.session.browser.source.json;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.io.BufferedReader;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import java.util.logging.Level;
import java.util.logging.Logger;

/** JSONL 对象节点读取器。 */
public final class JsonlObjectReader {

  private JsonlObjectReader() {}

  /** 读取 JSONL 文件中的对象节点；空行、非对象行和坏行会被跳过。 */
  public static List<JsonNode> readObjects(
      Path path, Logger logger, String badLineMessage, String readFailurePrefix) {
    List<JsonNode> objects = new ArrayList<>();
    ObjectMapper mapper = new ObjectMapper();
    try (BufferedReader reader = Files.newBufferedReader(path, StandardCharsets.UTF_8)) {
      String line;
      while ((line = reader.readLine()) != null) {
        String trimmed = line.trim();
        if (trimmed.isEmpty()) {
          continue;
        }
        try {
          JsonNode node = mapper.readTree(trimmed);
          if (node.isObject()) {
            objects.add(node);
          }
        } catch (IOException e) {
          logger.log(Level.FINE, badLineMessage, e);
        }
      }
    } catch (IOException e) {
      logger.log(Level.FINE, readFailurePrefix + path, e);
      return List.of();
    }
    return List.copyOf(objects);
  }
}
