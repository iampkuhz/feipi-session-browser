/**
 * 泛型 record。
 *
 * @param value 包装值
 * @param label 标签说明
 * @param <T>   值类型
 */
public record GenericValidRecord<T>(T value, String label) {
}
