/**
 * 带注解的 record。
 *
 * @param id    唯一标识
 * @param value 数据值
 */
@SuppressWarnings("all")
public record AnnotatedValidRecord(long id, String value) {
}
