/**
 * 外层容器。
 */
public class NestedValidRecord {

    /**
     * 嵌套 record。
     *
     * @param x 横坐标
     * @param y 纵坐标
     */
    public record InnerRecord(int x, int y) {
    }
}
