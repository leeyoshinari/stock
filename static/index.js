const pageSize = 20;
let page = 1;
document.getElementById("search").addEventListener("click", () => {
    page = 1; getStockList();
})

document.getElementById("pre-page").addEventListener("click", () => {
    page -= 1;
    if (page <= 1) {
        document.getElementById("pre-page").disabled = 'true';
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
                let neng;
                if (zhang >= 1 && item.qrr >= 2) {
                    neng = '放量上涨';
                } else if (zhang >= 1 && item.qrr <= 0.7) {
                    neng = '缩量上涨';
                } else if (zhang <= -1 && item.qrr >= 1.5) {
                    neng = '放量下跌';
                } else if (zhang <= -1 && item.qrr <= 0.7) {
                    neng = '缩量下跌';
                } else {
                    neng = '';
                }
                s += `<div id="${item.code}" class="item-list" style="color:${color};"><div>${item.name}</div><div>${item.code}</div><div>${item.current_price}</div><div>${zhang.toFixed(2)}%</div><div>${zhen.toFixed(2)}%</div>
                      <div>${item.volumn}</div><div>${item.qrr}</div><div>${neng}</div><div><button onclick="get_stock_figure('${item.code}', '${item.name}');">K线</button><button onclick="get_stock_figure();">推荐值</button></div></div>`;
            })
            document.getElementsByClassName("list")[0].innerHTML = s;
            if (page === parseInt((data.total + pageSize -1) / pageSize)) {
                document.getElementById("next-page").disabled = 'true';
            }
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
                plot_k_line(stockChart, `${name} - ${code}`, data.data.x, data.data.price, data.data.volumn, data.data.ma_three, data.data.ma_five, data.data.ma_ten, data.data.ma_twenty, data.data.qrr);
                document.getElementsByClassName("stock-chart")[0].style.display = "flex";
            }
        })
}

const overlay = document.querySelector('.stock-chart');
overlay.addEventListener('click', function(event) {
  if (event.target === overlay) {
    overlay.style.display = 'none';
  }
});

document.getElementById("pre-page").disabled = 'true';
getStockList();
