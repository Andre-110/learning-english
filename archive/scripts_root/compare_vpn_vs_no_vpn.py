"""
对比VPN关闭前后的100轮对话测试结果
"""
import json
import numpy as np
from scipy import stats

def load_results(filename):
    """加载测试结果"""
    try:
        with open(filename, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        return None

def analyze_outliers(times):
    """分析异常值"""
    q1 = np.percentile(times, 25)
    q3 = np.percentile(times, 75)
    iqr = q3 - q1
    upper_bound = q3 + 1.5 * iqr
    
    outliers = [t for t in times if t > upper_bound]
    mild_outliers = [t for t in outliers if t <= upper_bound * 2]
    severe_outliers = [t for t in outliers if t > upper_bound * 2]
    
    return {
        "threshold": upper_bound,
        "count": len(outliers),
        "percentage": len(outliers) / len(times) * 100,
        "mild_count": len(mild_outliers),
        "severe_count": len(severe_outliers),
        "avg_outlier_time": np.mean(outliers) if outliers else 0,
        "max_outlier_time": max(outliers) if outliers else 0
    }

def main():
    print("=" * 100)
    print("VPN关闭前后对比分析")
    print("=" * 100)
    
    # 加载结果
    results_with_vpn = load_results("conversation_100_turns_results.json")
    results_no_vpn = load_results("conversation_100_turns_results_no_vpn.json")
    
    if not results_with_vpn:
        print("❌ 未找到VPN开启时的测试结果")
        return
    
    if not results_no_vpn:
        print("❌ 未找到VPN关闭时的测试结果")
        print("   请等待测试完成...")
        return
    
    times_with_vpn = results_with_vpn["timing_analysis"]["all_times"]
    times_no_vpn = results_no_vpn["timing_analysis"]["all_times"]
    
    print(f"\n📊 基本统计对比")
    print("=" * 100)
    print(f"{'指标':<30} {'VPN开启':<20} {'VPN关闭':<20} {'变化':<15}")
    print("-" * 100)
    
    # 平均时间
    avg_with = np.mean(times_with_vpn)
    avg_no = np.mean(times_no_vpn)
    avg_change = ((avg_no / avg_with - 1) * 100) if avg_with > 0 else 0
    print(f"{'平均处理时间':<30} {avg_with:>8.2f}s{'':<11} {avg_no:>8.2f}s{'':<11} {avg_change:>+6.1f}%")
    
    # 中位数
    median_with = np.median(times_with_vpn)
    median_no = np.median(times_no_vpn)
    median_change = ((median_no / median_with - 1) * 100) if median_with > 0 else 0
    print(f"{'中位数处理时间':<30} {median_with:>8.2f}s{'':<11} {median_no:>8.2f}s{'':<11} {median_change:>+6.1f}%")
    
    # 最快
    min_with = min(times_with_vpn)
    min_no = min(times_no_vpn)
    min_change = ((min_no / min_with - 1) * 100) if min_with > 0 else 0
    print(f"{'最快处理时间':<30} {min_with:>8.2f}s{'':<11} {min_no:>8.2f}s{'':<11} {min_change:>+6.1f}%")
    
    # 最慢
    max_with = max(times_with_vpn)
    max_no = max(times_no_vpn)
    max_change = ((max_no / max_with - 1) * 100) if max_with > 0 else 0
    print(f"{'最慢处理时间':<30} {max_with:>8.2f}s{'':<11} {max_no:>8.2f}s{'':<11} {max_change:>+6.1f}%")
    
    # 标准差
    std_with = np.std(times_with_vpn)
    std_no = np.std(times_no_vpn)
    std_change = ((std_no / std_with - 1) * 100) if std_with > 0 else 0
    print(f"{'标准差':<30} {std_with:>8.2f}s{'':<11} {std_no:>8.2f}s{'':<11} {std_change:>+6.1f}%")
    
    # 总耗时
    total_with = results_with_vpn["total_time_seconds"]
    total_no = results_no_vpn["total_time_seconds"]
    total_change = ((total_no / total_with - 1) * 100) if total_with > 0 else 0
    print(f"{'总耗时':<30} {total_with/60:>8.1f}分钟{'':<11} {total_no/60:>8.1f}分钟{'':<11} {total_change:>+6.1f}%")
    
    # 异常值分析
    print(f"\n📊 异常值对比")
    print("=" * 100)
    
    outliers_with = analyze_outliers(times_with_vpn)
    outliers_no = analyze_outliers(times_no_vpn)
    
    print(f"{'指标':<30} {'VPN开启':<20} {'VPN关闭':<20} {'变化':<15}")
    print("-" * 100)
    print(f"{'异常值阈值':<30} {outliers_with['threshold']:>8.2f}s{'':<11} {outliers_no['threshold']:>8.2f}s{'':<11}")
    print(f"{'异常值数量':<30} {outliers_with['count']:>8d}个{'':<11} {outliers_no['count']:>8d}个{'':<11} {outliers_no['count'] - outliers_with['count']:>+6d}个")
    print(f"{'异常值占比':<30} {outliers_with['percentage']:>8.1f}%{'':<11} {outliers_no['percentage']:>8.1f}%{'':<11} {outliers_no['percentage'] - outliers_with['percentage']:>+6.1f}%")
    print(f"{'轻度异常值':<30} {outliers_with['mild_count']:>8d}个{'':<11} {outliers_no['mild_count']:>8d}个{'':<11} {outliers_no['mild_count'] - outliers_with['mild_count']:>+6d}个")
    print(f"{'重度异常值':<30} {outliers_with['severe_count']:>8d}个{'':<11} {outliers_no['severe_count']:>8d}个{'':<11} {outliers_no['severe_count'] - outliers_with['severe_count']:>+6d}个")
    print(f"{'异常值平均时间':<30} {outliers_with['avg_outlier_time']:>8.2f}s{'':<11} {outliers_no['avg_outlier_time']:>8.2f}s{'':<11} {((outliers_no['avg_outlier_time'] / outliers_with['avg_outlier_time'] - 1) * 100) if outliers_with['avg_outlier_time'] > 0 else 0:>+6.1f}%")
    print(f"{'最大异常值':<30} {outliers_with['max_outlier_time']:>8.2f}s{'':<11} {outliers_no['max_outlier_time']:>8.2f}s{'':<11} {((outliers_no['max_outlier_time'] / outliers_with['max_outlier_time'] - 1) * 100) if outliers_with['max_outlier_time'] > 0 else 0:>+6.1f}%")
    
    # 时间分布对比
    print(f"\n📊 时间分布对比")
    print("=" * 100)
    
    bins = [0, 3, 5, 7, 10, 15, 20, 30, 50, 100]
    
    hist_with, _ = np.histogram(times_with_vpn, bins=bins)
    hist_no, _ = np.histogram(times_no_vpn, bins=bins)
    
    print(f"{'时间区间':<15} {'VPN开启':<15} {'VPN关闭':<15} {'变化':<15}")
    print("-" * 60)
    for i in range(len(bins) - 1):
        bin_label = f"{bins[i]:.0f}-{bins[i+1]:.0f}秒"
        count_with = hist_with[i]
        count_no = hist_no[i]
        pct_with = count_with / len(times_with_vpn) * 100
        pct_no = count_no / len(times_no_vpn) * 100
        change = count_no - count_with
        print(f"{bin_label:<15} {count_with:>3d} ({pct_with:>5.1f}%){'':<5} {count_no:>3d} ({pct_no:>5.1f}%){'':<5} {change:>+6d}")
    
    # 统计显著性检验
    print(f"\n📊 统计显著性检验")
    print("=" * 100)
    
    # t检验
    t_stat, p_value = stats.ttest_ind(times_with_vpn, times_no_vpn)
    print(f"t检验:")
    print(f"  t统计量: {t_stat:.4f}")
    print(f"  p值: {p_value:.6f}")
    if p_value < 0.05:
        print(f"  ✅ 统计显著 (p < 0.05) - VPN关闭前后有显著差异")
    else:
        print(f"  ⚠️  统计不显著 (p >= 0.05) - VPN关闭前后无显著差异")
    
    # Mann-Whitney U检验（非参数检验）
    u_stat, u_p_value = stats.mannwhitneyu(times_with_vpn, times_no_vpn, alternative='two-sided')
    print(f"\nMann-Whitney U检验（非参数）:")
    print(f"  U统计量: {u_stat:.4f}")
    print(f"  p值: {u_p_value:.6f}")
    if u_p_value < 0.05:
        print(f"  ✅ 统计显著 (p < 0.05) - VPN关闭前后有显著差异")
    else:
        print(f"  ⚠️  统计不显著 (p >= 0.05) - VPN关闭前后无显著差异")
    
    # 结论
    print(f"\n📊 结论")
    print("=" * 100)
    
    improvements = []
    regressions = []
    
    if avg_change < -5:
        improvements.append(f"✅ 平均处理时间改善 {abs(avg_change):.1f}%")
    elif avg_change > 5:
        regressions.append(f"⚠️  平均处理时间增加 {avg_change:.1f}%")
    
    if outliers_no['count'] < outliers_with['count']:
        improvements.append(f"✅ 异常值数量减少 {outliers_with['count'] - outliers_no['count']}个")
    elif outliers_no['count'] > outliers_with['count']:
        regressions.append(f"⚠️  异常值数量增加 {outliers_no['count'] - outliers_with['count']}个")
    
    if outliers_no['percentage'] < outliers_with['percentage']:
        improvements.append(f"✅ 异常值占比降低 {outliers_with['percentage'] - outliers_no['percentage']:.1f}%")
    elif outliers_no['percentage'] > outliers_with['percentage']:
        regressions.append(f"⚠️  异常值占比增加 {outliers_no['percentage'] - outliers_with['percentage']:.1f}%")
    
    if outliers_no['severe_count'] < outliers_with['severe_count']:
        improvements.append(f"✅ 重度异常值减少 {outliers_with['severe_count'] - outliers_no['severe_count']}个")
    elif outliers_no['severe_count'] > outliers_with['severe_count']:
        regressions.append(f"⚠️  重度异常值增加 {outliers_no['severe_count'] - outliers_with['severe_count']}个")
    
    if std_change < -10:
        improvements.append(f"✅ 稳定性提升（标准差降低 {abs(std_change):.1f}%）")
    elif std_change > 10:
        regressions.append(f"⚠️  稳定性下降（标准差增加 {std_change:.1f}%）")
    
    if improvements:
        print("\n改善:")
        for imp in improvements:
            print(f"  {imp}")
    
    if regressions:
        print("\n退步:")
        for reg in regressions:
            print(f"  {reg}")
    
    if not improvements and not regressions:
        print("\n  ⚠️  VPN关闭前后无明显差异")
    
    print("\n" + "=" * 100)
    
    # 保存对比结果
    comparison = {
        "vpn_enabled": {
            "avg_time": avg_with,
            "median_time": median_with,
            "min_time": min_with,
            "max_time": max_with,
            "std_time": std_with,
            "total_time": total_with,
            "outliers": outliers_with
        },
        "vpn_disabled": {
            "avg_time": avg_no,
            "median_time": median_no,
            "min_time": min_no,
            "max_time": max_no,
            "std_time": std_no,
            "total_time": total_no,
            "outliers": outliers_no
        },
        "comparison": {
            "avg_change_percent": avg_change,
            "median_change_percent": median_change,
            "min_change_percent": min_change,
            "max_change_percent": max_change,
            "std_change_percent": std_change,
            "total_change_percent": total_change,
            "outlier_count_change": outliers_no['count'] - outliers_with['count'],
            "outlier_percentage_change": outliers_no['percentage'] - outliers_with['percentage'],
            "severe_outlier_change": outliers_no['severe_count'] - outliers_with['severe_count'],
            "statistical_test": {
                "t_test": {"t_stat": float(t_stat), "p_value": float(p_value)},
                "mannwhitney_u_test": {"u_stat": float(u_stat), "p_value": float(u_p_value)}
            }
        }
    }
    
    with open("vpn_comparison_results.json", 'w', encoding='utf-8') as f:
        json.dump(comparison, f, ensure_ascii=False, indent=2)
    
    print("\n对比结果已保存到: vpn_comparison_results.json")

if __name__ == "__main__":
    main()

