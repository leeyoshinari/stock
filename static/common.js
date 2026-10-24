function get_stock_figure(code) {
    show_modal_cover();
    let userId = localStorage.getItem('userId') || defaultUserId;
    fetch(`${prefix}/get?code=${code}&userId=${userId}`)
        .then(res => res.json())
        .then(data => {
            if (data.success) {
                let figure = document.getElementById("figure");
                figure.style.width = parseInt(document.body.clientWidth * 0.85) + 'px';
                figure.style.height = '';
                figure.removeAttribute("_echarts_instance_");
                figure.innerHTML = '';
                let profit = '';
                let isEtf = false;
                if (data.data.shares) {
                    profit = ` - 成本: ${data.data.cost}元, 数量: ${data.data.shares}股, 利润: ${data.data.profit}元`;
                }
                let region_str = ` - ${data.data.region}`;
                if (code.startsWith("1") || code.startsWith("5")){
                    region_str = '';
                    isEtf = true;
                    figure.style.height = '520px';
                }
                let title = `${data.data.name} - ${code}${region_str} - ${data.data.industry}${profit}`;
                let stockChart = echarts.init(figure);
                plot_k_line(stockChart, isEtf, title, data.data.x, data.data.price, data.data.volume, data.data.ma_five, data.data.ma_ten, data.data.ma_twenty, data.data.qrr, data.data.diff, data.data.dea, data.data.macd, data.data.k, data.data.d, data.data.j, data.data.total_shares, data.data.premium, data.data.turnover_rate, data.data.fund, data.data.boll_up, data.data.boll_low, data.data.coord);
                document.getElementsByClassName("stock-chart")[0].style.display = "flex";
            }
        })
        .finally(() => {close_modal_cover();})
}

function get_stock_real_figure(code) {
    show_modal_cover();
    fetch(`${prefix}/query/day/k?code=${code}`)
        .then(res => res.json())
        .then(data => {
            if (data.success) {
                let region_str = ` - ${data.data.region}`;
                if (code.startsWith("1") || code.startsWith("5")){
                    region_str = '';
                }
                let title = `${data.data.name} - ${code}${region_str} - ${data.data.industry}`;
                let figure = document.getElementById("figure");
                figure.style.width = parseInt(document.body.clientWidth * 0.85) + 'px';
                figure.style.height = '500px';
                figure.removeAttribute("_echarts_instance_")
                figure.innerHTML = '';
                let stockChart = echarts.init(figure);
                plot_minute_line(stockChart, title, data.data.x, data.data.price, data.data.price_avg, data.data.volume);
                document.getElementsByClassName("stock-chart")[0].style.display = "flex";
            }
        })
        .finally(() => {close_modal_cover();})
}

function show_modal_cover() {document.querySelectorAll('.modal_cover')[0].style.display = 'flex';document.querySelectorAll('.modal_cover>.modal_gif')[0].style.display = 'flex';}
function close_modal_cover() {document.querySelectorAll('.modal_cover')[0].style.display = 'none';document.querySelectorAll('.modal_cover>.modal_gif')[0].style.display = 'none';}

const overlay = document.querySelector('.stock-chart');
overlay.addEventListener('click', function(event) {
  if (event.target === overlay) {overlay.style.display = 'none';}
});

const overlay_data = document.querySelector('.stock-data');
overlay_data.addEventListener('click', function(event) {
  if (event.target === overlay_data) {overlay_data.style.display = 'none';}
});