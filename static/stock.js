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

function getStockRegion(code) {
    if (code.startsWith("60") || code.startsWith("68")) {
        return "sh"
    } else {
        return "sz"
    }
}

function getStockList() {
    let filter = document.getElementById("filter-by").value;
    let region = document.getElementById("stock-region").value;
    let industry = document.getElementById("stock-industry").value;
    let concept = document.getElementById("stock-concept").value;
    let url = prefix + `/stock/list?pageSize=20&page=${page}`;
    let stock_name = document.getElementById("stock-name").value;
    let stock_code = document.getElementById("stock-code").value;
    if (stock_code || stock_code.trim()) {
        url = url + `&code=${stock_code}`;
    }
    if (stock_name || stock_name.trim()) {
        url = url + `&name=${stock_name}`;
    }
    if (filter || filter.trim()) {
        url = url + `&filter=${filter}`;
    }
    if (region || region.trim()) {
        url = url + `&region=${region}`;
    }
    if (industry || industry.trim()) {
        url = url + `&industry=${industry}`;
    }
    if (concept || concept.trim()) {
        url = url + `&concept=${concept}`;
    }
    let showFlag = window.location.href.endsWith("trump");
    fetch(url)
        .then(res => res.json())
        .then(data => {
            let s = ""
            data.data.forEach(item => {
                s += `<div id="${item.code}" class="item-list"><div><a style="cursor:pointer;" onclick="get_stock_figure('${item.code}');">${item.name}</a><img id="show-${item.code}" src="${prefix}/static/copy.svg" alt="" style="display:none;" /></div><div><a style="cursor:pointer;" onclick="click_stock_code('${item.code}', '${item.filter}');">${item.code}</a><img id="copy-${item.code}" src="${prefix}/static/copy.svg" alt="" /></div><div>${item.region}</div><div>${item.industry}</div>
                      <div id="concept-${item.code}" onclick="show_concept('${item.code}');">${item.concept}</div></div>`;
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
            document.querySelectorAll('[id*="show-"]').forEach( item => {
                item.addEventListener('click', (event) => {
                    show_stock_filter(event.target.id.split('-')[1]);
                })
                if (showFlag) {item.style.display = "";}
            })
        })
}

function change_select() {page = 1;getStockList();}

function get_stock_figure(code) {
    fetch(prefix + `/get?code=${code}`)
        .then(res => res.json())
        .then(data => {
            if (data.success) {
                let title = `${data.data.name} - ${code} - ${data.data.region} - ${data.data.industry}`;
                let figure = document.getElementById("figure");
                figure.style.height = '';
                figure.removeAttribute("_echarts_instance_")
                figure.innerHTML = '';
                let stockChart = echarts.init(figure);
                plot_k_line(stockChart, title, data.data.x, data.data.price, data.data.volumn, data.data.ma_five, data.data.ma_ten, data.data.ma_twenty, data.data.qrr, data.data.diff, data.data.dea, data.data.macd, data.data.k, data.data.d, data.data.j, data.data.trix, data.data.trma, data.data.turnover_rate, data.data.fund);
                document.getElementsByClassName("stock-chart")[0].style.display = "flex";
            }
        })
}

function click_stock_code(code, flag) {
    if (flag.indexOf("myself") < 0) {
        let scode = getStockRegion(code) + code;
        window.open("https://quote.eastmoney.com/concept/" + scode + ".html#chart-k-cyq");
    } else {
        fetch(prefix + `/query/recommend/real?code=${code}`)
        .then(res => res.json())
        .then(data => {
            if (data.success) {
                let title = `${data.data.name} - ${code} - ${data.data.region} - ${data.data.industry}`;
                let figure = document.getElementById("figure");
                figure.style.height = '500px';
                figure.removeAttribute("_echarts_instance_")
                figure.innerHTML = '';
                let stockChart = echarts.init(figure);
                plot_minute_line(stockChart, title, data.data.x, data.data.price, data.data.volume);
                document.getElementsByClassName("stock-chart")[0].style.display = "flex";
            }
        })
    }
}

function show_stock_filter(code) {
    let s = `<div class="header">${code}</div><div><div class="title"><label>标签：</label><input type="text" id="filter-values" placeholder=""></div><div><button onclick="set_stock_filter('${code}', 1);">设置</button><button onclick="set_stock_filter('${code}', 0);">删除</button></div></div>`;
    document.getElementById("data-tips").innerHTML = s;
    document.getElementsByClassName("stock-data")[0].style.display = "flex";
}

function show_concept(code) {
    let codeEle = document.getElementById('concept-' + code);
    document.getElementById("data-tips").innerText = code + '\n' + codeEle.innerText;
    document.getElementsByClassName("stock-data")[0].style.display = "flex";
}

function set_stock_filter(code, value) {
    let filter = document.getElementById("filter-values").value;
    fetch(prefix + `/stock/setFilter?code=${code}&filter=${filter}&operate=${value}`)
        .then(res => res.json())
        .then(data => {
            if (!data.success) {alert(data.msg);}
        })
}

function show_modal_cover() {document.querySelectorAll('.modal_cover')[0].style.display = 'flex';document.querySelectorAll('.modal_cover>.modal_gif')[0].style.display = 'flex';}
function close_modal_cover() {document.querySelectorAll('.modal_cover')[0].style.display = 'none';document.querySelectorAll('.modal_cover>.modal_gif')[0].style.display = 'none';}

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
