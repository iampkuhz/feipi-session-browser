package com.feipi.session.browser.web.model;

/**
 * 分页状态不可变模型。
 *
 * <p>封装模板渲染分页控件所需的全部计算字段。所有校验在紧凑构造器完成，下游信任已验证的值。 通过 {@link #of(int, int, int)} 工厂方法从原始分页参数计算完整状态。
 *
 * <p>校验放置：页码和页面大小在 HTTP adapter 入口校验一次，本模型信任已验证的 int 值， 仅在构造器中做防御性边界检查。
 *
 * @param page 当前页码，从 1 开始
 * @param pageSize 每页条数
 * @param totalItems 总条目数
 * @param totalPages 总页数
 * @param pageStart 当前页第一条的显示序号，从 1 开始
 * @param pageEnd 当前页最后一条的显示序号，从 1 开始
 * @param hasPrev 是否存在上一页
 * @param hasNext 是否存在下一页
 */
public record PaginationModel(
    int page,
    int pageSize,
    int totalItems,
    int totalPages,
    int pageStart,
    int pageEnd,
    boolean hasPrev,
    boolean hasNext) {

  /**
   * 紧凑构造器，执行基本边界校验。
   *
   * @throws IllegalArgumentException page 小于 1 或 pageSize 小于 1
   */
  public PaginationModel {
    if (page < 1) {
      throw new IllegalArgumentException("页码必须 >= 1: " + page);
    }
    if (pageSize < 1) {
      throw new IllegalArgumentException("页面大小必须 >= 1: " + pageSize);
    }
  }

  /**
   * 从原始分页参数计算完整分页模型。
   *
   * <p>{@code totalItems} 为 0 时返回 page=1 的空分页模型。{@code page} 超出总页数时自动修正为最后一页。
   *
   * @param page 请求页码，从 1 开始
   * @param pageSize 每页条数，必须 >= 1
   * @param totalItems 总条目数，>= 0
   * @return 计算完成的分页模型
   */
  public static PaginationModel of(int page, int pageSize, int totalItems) {
    if (page < 1) {
      page = 1;
    }
    if (pageSize < 1) {
      pageSize = 1;
    }
    int safeTotal = Math.max(0, totalItems);
    int totalPages = safeTotal == 0 ? 1 : (int) Math.ceil((double) safeTotal / pageSize);
    int clampedPage = Math.min(page, totalPages);
    int start = (clampedPage - 1) * pageSize + 1;
    int end = Math.min(clampedPage * pageSize, safeTotal);
    return new PaginationModel(
        clampedPage,
        pageSize,
        safeTotal,
        totalPages,
        start,
        end,
        clampedPage > 1,
        clampedPage < totalPages);
  }
}
