/**
 * 实现接口的 record。
 *
 * @param code 状态码
 * @param text 状态文本
 */
public record ImplementsValidRecord(int code, String text) implements Comparable<ImplementsValidRecord> {

    @Override
    public int compareTo(ImplementsValidRecord other) {
        return Integer.compare(this.code, other.code);
    }
}
