"""
图片报告生成器
将每日报告生成为图片格式
"""

from PIL import Image, ImageDraw, ImageFont
from datetime import datetime
import os


class ImageReportGenerator:
    """图片报告生成器"""

    def __init__(self, width=1200):
        """
        初始化生成器

        Args:
            width: 图片宽度（像素）
        """
        self.width = width
        self.padding = 40
        self.line_height = 35
        self.current_y = 0

        # 颜色定义
        self.colors = {
            'bg': '#FFFFFF',
            'bg_section': '#F8F9FA',
            'text_dark': '#2C3E50',
            'text_medium': '#34495E',
            'text_light': '#7F8C8D',
            'primary': '#3498DB',
            'btc': '#F39C12',
            'eth': '#627EEA',
            'red': '#E74C3C',
            'green': '#27AE60',
            'border': '#ECF0F1'
        }

        # 字体（使用系统默认字体）
        try:
            self.font_title = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 36)
            self.font_heading = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 24)
            self.font_subheading = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 18)
            self.font_normal = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 16)
            self.font_small = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 14)
        except:
            # 如果找不到字体，使用默认字体
            self.font_title = ImageFont.load_default()
            self.font_heading = ImageFont.load_default()
            self.font_subheading = ImageFont.load_default()
            self.font_normal = ImageFont.load_default()
            self.font_small = ImageFont.load_default()

    def hex_to_rgb(self, hex_color):
        """将十六进制颜色转换为RGB"""
        hex_color = hex_color.lstrip('#')
        return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))

    def draw_section_box(self, draw, y, height, bg_color='bg_section'):
        """绘制章节背景框"""
        draw.rectangle(
            [self.padding, y, self.width - self.padding, y + height],
            fill=self.hex_to_rgb(self.colors[bg_color]),
            outline=self.hex_to_rgb(self.colors['border']),
            width=1
        )

    def draw_text_with_bg(self, draw, text, x, y, font, text_color, bg_color=None, padding=10):
        """绘制带背景的文本"""
        bbox = draw.textbbox((x, y), text, font=font)

        if bg_color:
            draw.rectangle(
                [bbox[0] - padding, bbox[1] - padding, bbox[2] + padding, bbox[3] + padding],
                fill=self.hex_to_rgb(self.colors[bg_color])
            )

        draw.text((x, y), text, fill=self.hex_to_rgb(self.colors[text_color]), font=font)
        return bbox[3] - bbox[1]

    def generate_report_image(self, report_data, output_path):
        """
        生成报告图片

        Args:
            report_data: 报告数据字典
            output_path: 输出图片路径
        """
        # 第一遍：计算所需高度
        estimated_height = self._calculate_height(report_data)

        # 创建图片
        img = Image.new('RGB', (self.width, estimated_height), self.hex_to_rgb(self.colors['bg']))
        draw = ImageDraw.Draw(img)

        self.current_y = self.padding

        # 1. 标题
        self._draw_title(draw)

        # 2. 时间范围
        self._draw_time_range(draw, report_data['time_range'])

        # 3. 市场指标
        self._draw_market_metrics(draw, report_data['spot_prices'])

        # 4. 交易统计
        self._draw_trade_stats(draw, report_data['trade_statistics'])

        # 5. BTC Top 3
        self._draw_coin_section(draw, 'BTC', report_data['top_trades'])

        # 6. ETH Top 3
        self._draw_coin_section(draw, 'ETH', report_data['top_trades'])

        # 7. 页脚
        self._draw_footer(draw, report_data['generated_at'])

        # 保存图片
        img.save(output_path, 'PNG', quality=95)
        return output_path

    def _calculate_height(self, report_data):
        """计算图片所需高度"""
        height = 100  # 标题
        height += 150  # 时间范围
        height += 150  # 市场指标
        height += 150  # 交易统计

        # BTC 部分
        btc_trades = (
            len(report_data['top_trades'].get('btc_by_amount', [])) +
            len(report_data['top_trades'].get('btc_by_volume', []))
        )
        height += 100 + btc_trades * 250  # 每笔交易约250px

        # ETH 部分
        eth_trades = (
            len(report_data['top_trades'].get('eth_by_amount', [])) +
            len(report_data['top_trades'].get('eth_by_volume', []))
        )
        height += 100 + eth_trades * 250

        height += 100  # 页脚

        return height

    def _draw_title(self, draw):
        """绘制标题"""
        title = "📊 SignalPlus Trade Alert 每日报告"
        bbox = draw.textbbox((0, 0), title, font=self.font_title)
        text_width = bbox[2] - bbox[0]
        x = (self.width - text_width) // 2

        draw.text((x, self.current_y), title,
                 fill=self.hex_to_rgb(self.colors['text_dark']),
                 font=self.font_title)

        self.current_y += 60

        # 分隔线
        draw.line(
            [self.padding, self.current_y, self.width - self.padding, self.current_y],
            fill=self.hex_to_rgb(self.colors['primary']),
            width=3
        )
        self.current_y += 30

    def _draw_time_range(self, draw, time_range):
        """绘制时间范围"""
        section_height = 120
        self.draw_section_box(draw, self.current_y, section_height)

        y = self.current_y + 20
        x = self.padding + 20

        draw.text((x, y), "📅 统计时间范围",
                 fill=self.hex_to_rgb(self.colors['text_dark']),
                 font=self.font_heading)
        y += 40

        draw.text((x, y), f"开始: {time_range['start']}",
                 fill=self.hex_to_rgb(self.colors['text_medium']),
                 font=self.font_normal)
        y += 30

        draw.text((x, y), f"结束: {time_range['end']}",
                 fill=self.hex_to_rgb(self.colors['text_medium']),
                 font=self.font_normal)

        self.current_y += section_height + 20

    def _draw_market_metrics(self, draw, spot_prices):
        """绘制市场指标"""
        section_height = 120
        self.draw_section_box(draw, self.current_y, section_height)

        y = self.current_y + 20
        x = self.padding + 20

        draw.text((x, y), "💰 市场指标",
                 fill=self.hex_to_rgb(self.colors['text_dark']),
                 font=self.font_heading)
        y += 50

        # BTC 和 ETH 并排显示
        btc_text = f"BTC: ${spot_prices['btc']:,.2f}"
        draw.text((x, y), btc_text,
                 fill=self.hex_to_rgb(self.colors['btc']),
                 font=self.font_heading)

        eth_text = f"ETH: ${spot_prices['eth']:,.2f}"
        draw.text((x + 300, y), eth_text,
                 fill=self.hex_to_rgb(self.colors['eth']),
                 font=self.font_heading)

        self.current_y += section_height + 20

    def _draw_trade_stats(self, draw, stats):
        """绘制交易统计"""
        section_height = 120
        self.draw_section_box(draw, self.current_y, section_height)

        y = self.current_y + 20
        x = self.padding + 20

        draw.text((x, y), "📈 大宗交易统计",
                 fill=self.hex_to_rgb(self.colors['text_dark']),
                 font=self.font_heading)
        y += 50

        stats_text = f"总笔数: {stats['total']}  |  BTC: {stats['btc_count']}  |  ETH: {stats['eth_count']}"
        draw.text((x, y), stats_text,
                 fill=self.hex_to_rgb(self.colors['text_medium']),
                 font=self.font_normal)

        self.current_y += section_height + 20

    def _draw_coin_section(self, draw, coin, top_trades):
        """绘制币种部分（BTC或ETH）"""
        coin_color = 'btc' if coin == 'BTC' else 'eth'
        emoji = '🔶' if coin == 'BTC' else '🔷'

        # 币种标题
        draw.text((self.padding + 20, self.current_y),
                 f"{emoji} {coin} 交易",
                 fill=self.hex_to_rgb(self.colors[coin_color]),
                 font=self.font_heading)
        self.current_y += 50

        # 按金额 Top 3
        key_amount = f'{coin.lower()}_by_amount'
        if top_trades.get(key_amount):
            self._draw_top_category(draw, f"💰 按金额排名 Top 3",
                                   top_trades[key_amount], 'amount')

        # 按数量 Top 3
        key_volume = f'{coin.lower()}_by_volume'
        if top_trades.get(key_volume):
            self._draw_top_category(draw, f"📦 按数量排名 Top 3",
                                   top_trades[key_volume], 'volume')

    def _draw_top_category(self, draw, title, trades, sort_type):
        """绘制Top分类"""
        draw.text((self.padding + 40, self.current_y), title,
                 fill=self.hex_to_rgb(self.colors['text_dark']),
                 font=self.font_subheading)
        self.current_y += 40

        for trade in trades:
            self._draw_trade_card(draw, trade, sort_type)

    def _draw_trade_card(self, draw, trade, sort_type):
        """绘制交易卡片"""
        card_height = 230
        x = self.padding + 60
        y_start = self.current_y

        # 背景框
        draw.rectangle(
            [x, y_start, self.width - self.padding - 20, y_start + card_height],
            fill=self.hex_to_rgb(self.colors['bg']),
            outline=self.hex_to_rgb(self.colors['red']),
            width=3
        )

        y = y_start + 15
        x_text = x + 15

        # 标题行
        header = f"#{trade['rank']} - {trade['date']} - {trade['strategy']}"
        draw.text((x_text, y), header,
                 fill=self.hex_to_rgb(self.colors['red']),
                 font=self.font_subheading)
        y += 35

        # 关键指标（高亮）
        if sort_type == 'amount':
            highlight = f"💰 ${trade['amount_usd']:,.2f}"
        else:
            highlight = f"📦 {trade['volume']}x"

        draw.text((x_text, y), highlight,
                 fill=self.hex_to_rgb(self.colors['red']),
                 font=self.font_heading)
        y += 40

        # 详细信息
        details = [
            f"合约: {trade['contract']}",
            f"价格: {trade['price']}  |  IV: {trade['iv']}"
        ]

        for detail in details:
            draw.text((x_text, y), detail,
                     fill=self.hex_to_rgb(self.colors['text_medium']),
                     font=self.font_small)
            y += 25

        # 希腊字母
        y += 10
        greeks_text = f"Delta: {trade['greeks']['delta'] or 'N/A'}  |  "
        greeks_text += f"Gamma: {trade['greeks']['gamma'] or 'N/A'}  |  "
        greeks_text += f"Vega: {trade['greeks']['vega'] or 'N/A'}  |  "
        greeks_text += f"Theta: {trade['greeks']['theta'] or 'N/A'}  |  "
        greeks_text += f"Rho: {trade['greeks']['rho'] or 'N/A'}"

        draw.text((x_text, y), greeks_text,
                 fill=self.hex_to_rgb(self.colors['text_light']),
                 font=self.font_small)

        self.current_y += card_height + 15

    def _draw_footer(self, draw, generated_at):
        """绘制页脚"""
        self.current_y += 20
        footer_text = f"生成时间: {generated_at}"

        bbox = draw.textbbox((0, 0), footer_text, font=self.font_small)
        text_width = bbox[2] - bbox[0]
        x = (self.width - text_width) // 2

        draw.text((x, self.current_y), footer_text,
                 fill=self.hex_to_rgb(self.colors['text_light']),
                 font=self.font_small)

        self.current_y += 40


def generate_image_report(report_data, output_dir='tests/reports_preview'):
    """
    生成图片格式的报告

    Args:
        report_data: 报告数据字典
        output_dir: 输出目录

    Returns:
        生成的图片路径
    """
    os.makedirs(output_dir, exist_ok=True)

    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    output_path = os.path.join(output_dir, f'daily_report_{timestamp}.png')

    generator = ImageReportGenerator(width=1200)
    generator.generate_report_image(report_data, output_path)

    return output_path


if __name__ == '__main__':
    # 测试代码
    test_data = {
        'generated_at': datetime.now().isoformat(),
        'time_range': {
            'start': '2025-12-10 16:00:00 CST',
            'end': '2025-12-11 16:00:00 CST',
            'timezone': 'Asia/Shanghai'
        },
        'spot_prices': {
            'btc': 102992.00,
            'eth': 3423.82
        },
        'trade_statistics': {
            'total': 292,
            'btc_count': 208,
            'eth_count': 84,
            'other_count': 0
        },
        'top_trades': {
            'btc_by_amount': [],
            'btc_by_volume': [],
            'eth_by_amount': [],
            'eth_by_volume': []
        }
    }

    output = generate_image_report(test_data)
    print(f"测试图片已生成: {output}")
