"""系统资源监控模块。

监控 CPU、内存、温度，防止过热和资源不足。
"""

import asyncio
import logging
import platform
import shutil
import subprocess
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class SystemResources:
    """系统资源状态"""

    cpu_percent: float  # CPU 使用率 0-100
    memory_percent: float  # 内存使用率 0-100
    memory_used_gb: float  # 已用内存 GB
    memory_total_gb: float  # 总内存 GB
    temperature: Optional[float] = None  # CPU 温度（如果能获取）
    is_safe: bool = True  # 是否安全继续任务
    warning: Optional[str] = None  # 警告信息


class ResourceMonitor:
    """资源监控器"""

    def __init__(
        self,
        max_cpu_percent: float = 85.0,  # CPU 可以较高
        max_memory_percent: float = 96.0,  # 内存阈值临时放宽到 96%
        max_temperature: float = 85.0,  # 安全温度
        check_interval: float = 2.0,
    ):
        self.max_cpu_percent = max_cpu_percent
        self.max_memory_percent = max_memory_percent
        self.max_temperature = max_temperature
        self.check_interval = check_interval
        self._monitoring = False
        self._last_status: Optional[SystemResources] = None

    def check_resources(self) -> SystemResources:
        """检查系统资源状态"""
        # CPU 使用率
        cpu_percent = self._get_cpu_percent()

        # 内存使用
        memory_percent, memory_used_gb, memory_total_gb = self._get_memory_info()

        # CPU 温度
        temperature = self._get_temperature()

        # 判断是否安全
        warnings = []
        is_safe = True

        if cpu_percent > self.max_cpu_percent:
            is_safe = False
            warnings.append(f"CPU 使用率过高: {cpu_percent:.1f}% > {self.max_cpu_percent}%")

        if memory_percent > self.max_memory_percent:
            is_safe = False
            warnings.append(f"内存使用率过高: {memory_percent:.1f}% > {self.max_memory_percent}%")

        if temperature and temperature > self.max_temperature:
            is_safe = False
            warnings.append(f"CPU 温度过高: {temperature:.1f}°C > {self.max_temperature}°C")

        warning = "; ".join(warnings) if warnings else None
        self._last_status = SystemResources(
            cpu_percent=cpu_percent,
            memory_percent=memory_percent,
            memory_used_gb=memory_used_gb,
            memory_total_gb=memory_total_gb,
            temperature=temperature,
            is_safe=is_safe,
            warning=warning,
        )

        return self._last_status

    def _get_cpu_percent(self) -> float:
        """获取 CPU 使用率"""
        try:
            import psutil
            # 使用小 interval 获取准确的 CPU 使用率
            return psutil.cpu_percent(interval=0.1)
        except ImportError:
            # 如果没有 psutil，使用系统命令
            if platform.system() == "Darwin":  # macOS
                try:
                    result = subprocess.run(
                        ["top", "-l", "1", "-n", "0"],
                        capture_output=True,
                        text=True,
                        timeout=3,
                    )
                    # 解析 top 输出中的 CPU 空闲率
                    for line in result.stdout.split("\n"):
                        if "CPU usage" in line:
                            parts = line.split(",")
                            for part in parts:
                                if "idle" in part:
                                    val = part.strip().split()[0]
                                    val = val.rstrip("%")
                                    idle = float(val)
                                    return 100 - idle
                except Exception as e:
                    logger.warning(f"获取 CPU 使用率失败: {e}")
            return 0.0

    def _get_memory_info(self) -> tuple[float, float, float]:
        """获取内存信息 (使用率%, 已用GB, 总GB)"""
        try:
            import psutil
            mem = psutil.virtual_memory()
            return mem.percent, mem.used / (1024**3), mem.total / (1024**3)
        except ImportError:
            # 使用系统命令
            if platform.system() == "Darwin":  # macOS
                try:
                    # 获取总内存 - 使用完整路径
                    result = subprocess.run(
                        ["/usr/sbin/sysctl", "-n", "hw.memsize"],
                        capture_output=True,
                        text=True,
                        timeout=2,
                    )
                    total_bytes = int(result.stdout.strip())
                    total_gb = total_bytes / (1024**3)

                    # 获取内存页面信息
                    result = subprocess.run(
                        ["/usr/bin/vm_stat"],
                        capture_output=True,
                        text=True,
                        timeout=2,
                    )

                    # 解析 vm_stat 输出
                    # 获取页面大小（从第一行或默认值）
                    page_size = 16384  # macOS Apple Silicon 默认 16KB 页面

                    free_pages = 0
                    active_pages = 0
                    inactive_pages = 0
                    speculative_pages = 0
                    wired_pages = 0

                    for line in result.stdout.split("\n"):
                        line_lower = line.lower()
                        if "pages free" in line_lower:
                            free_pages = int(line.split(":")[1].strip().rstrip("."))
                        elif "pages active" in line_lower:
                            active_pages = int(line.split(":")[1].strip().rstrip("."))
                        elif "pages inactive" in line_lower:
                            inactive_pages = int(line.split(":")[1].strip().rstrip("."))
                        elif "pages speculative" in line_lower:
                            speculative_pages = int(line.split(":")[1].strip().rstrip("."))
                        elif "pages wired down" in line_lower:
                            wired_pages = int(line.split(":")[1].strip().rstrip("."))

                    # 已用内存 = active + inactive + wired
                    # 空闲内存 = free + speculative
                    used_bytes = (active_pages + inactive_pages + wired_pages) * page_size
                    used_gb = used_bytes / (1024**3)
                    percent = (used_gb / total_gb) * 100
                    return percent, used_gb, total_gb
                except Exception as e:
                    logger.warning(f"获取内存信息失败: {e}")
            return 0.0, 0.0, 0.0

    def _get_temperature(self) -> Optional[float]:
        """获取 CPU 温度"""
        try:
            if platform.system() == "Darwin":  # macOS
                # 尝试使用 osx-cpu-temp 或 powermetrics
                try:
                    result = subprocess.run(
                        ["powermetrics", "--samplers", "smc", "-i1", "-n1"],
                        capture_output=True,
                        text=True,
                        timeout=5,
                    )
                    # 解析输出寻找温度
                    for line in result.stdout.split("\n"):
                        if "die temperature" in line.lower():
                            # "CPU die temperature: 45.00 C"
                            temp_str = line.split(":")[1].strip().split()[0]
                            return float(temp_str)
                except Exception:
                    pass

                # 备用方案：尝试 osx-cpu-temp
                try:
                    result = subprocess.run(
                        ["osx-cpu-temp"],
                        capture_output=True,
                        text=True,
                        timeout=2,
                    )
                    if result.returncode == 0:
                        # 输出格式: "45.0°C"
                        temp_str = result.stdout.strip().rstrip("°C")
                        return float(temp_str)
                except FileNotFoundError:
                    pass

        except Exception as e:
            logger.debug(f"获取温度失败: {e}")

        return None

    def get_status_string(self) -> str:
        """获取状态字符串"""
        status = self._last_status or self.check_resources()

        parts = [
            f"CPU: {status.cpu_percent:.0f}%",
            f"内存: {status.memory_percent:.0f}% ({status.memory_used_gb:.1f}/{status.memory_total_gb:.1f}GB)",
        ]

        if status.temperature:
            parts.append(f"温度: {status.temperature:.0f}°C")

        if status.warning:
            parts.append(f"⚠️ {status.warning}")

        return " | ".join(parts)

    async def wait_for_resources(self, max_wait: float = 300.0) -> bool:
        """等待资源可用

        Args:
            max_wait: 最大等待时间（秒）

        Returns:
            资源是否可用
        """
        waited = 0.0
        while waited < max_wait:
            status = self.check_resources()
            if status.is_safe:
                return True

            logger.warning(f"资源不足，等待中: {status.warning}")
            await asyncio.sleep(self.check_interval)
            waited += self.check_interval

        logger.error(f"等待资源超时 ({max_wait}s)")
        return False


# 全局实例
resource_monitor = ResourceMonitor()


def check_system_resources() -> SystemResources:
    """检查系统资源（便捷函数）"""
    return resource_monitor.check_resources()


def is_safe_to_process() -> bool:
    """检查是否安全处理任务"""
    status = resource_monitor.check_resources()
    if not status.is_safe:
        logger.warning(f"资源检查未通过: {status.warning}")
    return status.is_safe