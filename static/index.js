const pageSize = 20;
let page = 1;
document.getElementById("search").addEventListener("click", () => {
    page = 1; getStockList();
})
document.addEventListener('keypress', function(event) {
    if (event.key === 'Enter') {
        page = 1; getStockList();
    }
});

document.getElementById("pre-page").addEventListener("click", () => {
    page -= 1;
    if (page <= 1) {
        document.getElementById("pre-page").disabled = 'true';
        document.getElementById("next-page").disabled = '';
    }
    getStockList();
})

document.getElementById("next-page").addEventListener("click", () => {
    page += 1;
    if (page > 1) {
        document.getElementById("pre-page").disabled = '';
    }
    getStockList();
})

function getStockList() {
    let sortField = document.getElementById("order-by").value;
    let url = prefix + `/list?pageSize=20&page=${page}&sortField=${sortField}`;
    let stock_name = document.getElementById("stock-name").value;
    let stock_code = document.getElementById("stock-code").value;
    if (stock_code || stock_code.trim()) {
        url = url + `&code=${stock_code}`;
    }
    if (stock_name || stock_name.trim()) {
        url = url + `&name=${stock_name}`;
    }
    fetch(url)
        .then(res => res.json())
        .then(data => {
            let s = ""
            data.data.forEach(item => {
                let zhang = (item.current_price - item.last_price) / item.last_price * 100;
                let zhen = (item.max_price - item.min_price) / item.last_price * 100;
                let color = zhang >= 0 ? zhang > 0 ? 'red' : 'black' : 'green';
                s += `<div id="${item.code}" class="item-list" style="color:${color};"><div><a style="cursor:pointer;" onclick="get_stock_figure('${item.code}', '${item.name}');">${item.name}</a></div><div>${item.code}<img id="copy-${item.code}" src="${prefix}/static/copy.svg" alt="" /></div><div>${item.current_price}</div><div>${zhang.toFixed(2)}%</div><div>${zhen.toFixed(2)}%</div>
                      <div>${item.volumn}</div><div>${item.qrr}</div><div>${item.turnover_rate}%</div><div>${item.fund.toFixed(0)}万</div></div>`;
            })
            document.getElementsByClassName("list")[0].innerHTML = s;
            if (page === parseInt((data.total + pageSize -1) / pageSize)) {
                document.getElementById("next-page").disabled = 'true';
            }
            document.querySelectorAll('[id*="copy-"]').forEach( item => {
                item.addEventListener('click', (event) => {
                    if (navigator.clipboard && window.isSecureContext) {
                        navigator.clipboard.writeText(event.target.id.split('-')[1]);
                    }
                })
            })
        })
}

function change_select() {page = 1;getStockList();}

function get_stock_figure(code, name) {
    fetch(prefix + `/get?code=${code}`)
        .then(res => res.json())
        .then(data => {
            if (data.success) {
                let figure = document.getElementById("figure");
                figure.removeAttribute("_echarts_instance_")
                figure.innerHTML = '';
                let stockChart = echarts.init(figure);
                plot_k_line(stockChart, `${name} - ${code}`, data.data.x, data.data.price, data.data.volumn, data.data.ma_five, data.data.ma_ten, data.data.ma_twenty, data.data.qrr, data.data.diff, data.data.dea, data.data.macd, data.data.k, data.data.d, data.data.j, data.data.trix, data.data.trma, data.data.turnover_rate, data.data.fund);
                document.getElementsByClassName("stock-chart")[0].style.display = "flex";
            }
        })
}

function get_stock_data(code, name) {
    fetch(prefix + `/getAverage?code=${code}&start_date=&end_date=`)
        .then(res => res.json())
        .then(data => {
            if (data.success) {
                let stock = data.data;
                let s = `<div class="header">${name} - ${code}</div><div><div class="title">价格-3日均线</div><div class="value"><div><span>L3D: </span><span class="value-text" style="color:${stock.price.ma3_angle_l3d >= 0 ? 'red' : 'green'}">${stock.price.ma3_angle_l3d}°</span><img src="${prefix}/static/${stock.price.ma3_angle_l3d >= 0 ? 'up' : 'down'}.svg" /></div><div><span>L5D: </span><span class="value-text" style="color:${stock.price.ma3_angle_l5d >= 0 ? 'red' : 'green'}">${stock.price.ma3_angle_l5d}°</span><img src="${prefix}/static/${stock.price.ma3_angle_l5d >= 0 ? 'up' : 'down'}.svg" /></div></div></div>
                <div><div class="title">价格-5日均线</div><div class="value"><div><span>L3D: </span><span class="value-text" style="color:${stock.price.ma5_angle_l3d >= 0 ? 'red' : 'green'}">${stock.price.ma5_angle_l3d}°</span><img src="${prefix}/static/${stock.price.ma5_angle_l3d >= 0 ? 'up' : 'down'}.svg" /></div><div><span>L5D: </span><span class="value-text" style="color:${stock.price.ma5_angle_l5d >= 0 ? 'red' : 'green'}">${stock.price.ma5_angle_l5d}°</span><img src="${prefix}/static/${stock.price.ma5_angle_l5d >= 0 ? 'up' : 'down'}.svg" /></div><div><span>L10D: </span><span class="value-text" style="color:${stock.price.ma5_angle_l10d >= 0 ? 'red' : 'green'}">${stock.price.ma5_angle_l10d}°</span><img src="${prefix}/static/${stock.price.ma5_angle_l10d >= 0 ? 'up' : 'down'}.svg" /></div><div><span>L20D: </span><span class="value-text" style="color:${stock.price.ma5_angle_l20d >= 0 ? 'red' : 'green'}">${stock.price.ma5_angle_l20d}°</span><img src="${prefix}/static/${stock.price.ma5_angle_l20d >= 0 ? 'up' : 'down'}.svg" /></div></div></div>
                <div><div class="title">价格-10日均线</div><div class="value"><div><span>L5D: </span><span class="value-text" style="color:${stock.price.ma10_angle_l5d >= 0 ? 'red' : 'green'}">${stock.price.ma10_angle_l5d}°</span><img src="${prefix}/static/${stock.price.ma10_angle_l5d >= 0 ? 'up' : 'down'}.svg" /></div><div><span>L10D: </span><span class="value-text" style="color:${stock.price.ma10_angle_l10d >= 0 ? 'red' : 'green'}">${stock.price.ma10_angle_l10d}°</span><img src="${prefix}/static/${stock.price.ma10_angle_l10d >= 0 ? 'up' : 'down'}.svg" /></div><div><span>L20D: </span><span class="value-text" style="color:${stock.price.ma10_angle_l20d >= 0 ? 'red' : 'green'}">${stock.price.ma10_angle_l20d}°</span><img src="${prefix}/static/${stock.price.ma10_angle_l20d >= 0 ? 'up' : 'down'}.svg" /></div></div></div>
                <div><div class="title">价格-20日均线</div><div class="value"><div><span>L5D: </span><span class="value-text" style="color:${stock.price.ma20_angle_l5d >= 0 ? 'red' : 'green'}">${stock.price.ma20_angle_l5d}°</span><img src="${prefix}/static/${stock.price.ma20_angle_l5d >= 0 ? 'up' : 'down'}.svg" /></div><div><span>L10D: </span><span class="value-text" style="color:${stock.price.ma20_angle_l10d >= 0 ? 'red' : 'green'}">${stock.price.ma20_angle_l10d}°</span><img src="${prefix}/static/${stock.price.ma20_angle_l10d >= 0 ? 'up' : 'down'}.svg" /></div><div><span>L20D: </span><span class="value-text" style="color:${stock.price.ma20_angle_l20d >= 0 ? 'red' : 'green'}">${stock.price.ma20_angle_l20d}°</span><img src="${prefix}/static/${stock.price.ma20_angle_l20d >= 0 ? 'up' : 'down'}.svg" /></div></div></div>
                <div><div class="title">成交量</div><div class="value"><div><span>L3D: </span><span class="value-text" style="color:${stock.volume.volume_angle_l3d >= 0 ? 'red' : 'green'}">${stock.volume.volume_angle_l3d}°</span><img src="${prefix}/static/${stock.volume.volume_angle_l3d >= 0 ? 'up' : 'down'}.svg" /></div><div><span>L5D: </span><span class="value-text" style="color:${stock.volume.volume_angle_l5d >= 0 ? 'red' : 'green'}">${stock.volume.volume_angle_l5d}°</span><img src="${prefix}/static/${stock.volume.volume_angle_l5d >= 0 ? 'up' : 'down'}.svg" /></div><div><span>L10D: </span><span class="value-text" style="color:${stock.volume.volume_angle_l10d >= 0 ? 'red' : 'green'}">${stock.volume.volume_angle_l10d}°</span><img src="${prefix}/static/${stock.volume.volume_angle_l10d >= 0 ? 'up' : 'down'}.svg" /></div><div><span>L20D: </span><span class="value-text" style="color:${stock.volume.volume_angle_l20d >= 0 ? 'red' : 'green'}">${stock.volume.volume_angle_l20d}°</span><img src="${prefix}/static/${stock.volume.volume_angle_l20d >= 0 ? 'up' : 'down'}.svg" /></div></div></div>
                <div><div class="title">量比(标准差)</div><div class="value"><div><span>L1D: </span><span class="value-text" style="color:${stock.volume.qrr_deviation_l1d >= 1 ? 'red' : 'green'}">${stock.volume.qrr_deviation_l1d}</span></div><div><span>L2D: </span><span class="value-text" style="color:${stock.volume.qrr_deviation_l2d >= 1 ? 'red' : 'green'}">${stock.volume.qrr_deviation_l2d}</span></div><div><span>L3D: </span><span class="value-text" style="color:${stock.volume.qrr_deviation_l3d >= 1 ? 'red' : 'green'}">${stock.volume.qrr_deviation_l3d}</span></div><div><span>L4D: </span><span class="value-text" style="color:${stock.volume.qrr_deviation_l4d >= 1 ? 'red' : 'green'}">${stock.volume.qrr_deviation_l4d}</span></div></div></div>
                <div><div class="title">实时成交量</div><div class="value"><div><span>L3D: </span><span class="value-text" style="color:${stock.real_volume.volumn_angle_l3d >= 0 ? 'red' : 'green'}">${stock.real_volume.volumn_angle_l3d}°</span><img src="${prefix}/static/${stock.real_volume.volumn_angle_l3d >= 0 ? 'up' : 'down'}.svg" /></div><div><span>L5D: </span><span class="value-text" style="color:${stock.real_volume.volumn_angle_l5d >= 0 ? 'red' : 'green'}">${stock.real_volume.volumn_angle_l5d}°</span><img src="${prefix}/static/${stock.real_volume.volumn_angle_l5d >= 0 ? 'up' : 'down'}.svg" /></div></div></div>`;
                document.getElementById("data-tips").innerHTML = s;
                document.getElementsByClassName("stock-data")[0].style.display = "flex";
            }
        })
}

function plot_stock_trend(code, name) {
    fetch(prefix + `/check?code=${code}`)
        .then(res => res.json())
        .then(data => {
            if (data.success) {
                let figure = document.getElementById("figure");
                figure.removeAttribute("_echarts_instance_")
                figure.innerHTML = '';
                let stockChart = echarts.init(figure);
                plot_trend(stockChart, `${name} - ${code}`, data.data.x, data.data.y1, data.data.y3, data.data.y5, data.data.price1, data.data.price3, data.data.price5);
                document.getElementsByClassName("stock-chart")[0].style.display = "flex";
            }
        })
}

const overlay = document.querySelector('.stock-chart');
const overlay_data = document.querySelector('.stock-data');
overlay.addEventListener('click', function(event) {
  if (event.target === overlay) {overlay.style.display = 'none';}
});
overlay_data.addEventListener('click', function(event) {
  if (event.target === overlay_data) {overlay_data.style.display = 'none';}
});

document.getElementById("pre-page").disabled = 'true';
getStockList();
