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
    let url = prefix + `/getRecommend?page=${page}`;
    fetch(url)
        .then(res => res.json())
        .then(data => {
            let s = ""
            data.data.forEach(item => {
                s += `<div id="${item.code}" class="item-list" style="height:90px;"><div>${item.name}</div><div>${item.code}</div><div>${item.price}</div><div>${item.create_time}</div><div class="three-price"><span style="color:${item.last_one_price>0 ? "red" : item.last_one_price<0 ? "green" : "black"};">收:${item.last_one_price}%</span><span style="color:${item.last_one_high>0 ? "red" : item.last_one_high<0 ? "green" : "black"};">高:${item.last_one_high}%</span><span style="color:${item.last_one_low>0 ? "red" : item.last_one_low<0 ? "green" : "black"};">低:${item.last_one_low}%</span></div>
                      <div class="three-price"><span style="color:${item.last_two_price>0 ? "red" : item.last_two_price<0 ? "green" : "black"};">收:${item.last_two_price}%</span><span style="color:${item.last_two_high>0 ? "red" : item.last_two_high<0 ? "green" : "black"};">高:${item.last_two_high}%</span><span style="color:${item.last_two_low>0 ? "red" : item.last_two_low<0 ? "green" : "black"};">低:${item.last_two_low}%</span></div>
                      <div class="three-price"><span style="color:${item.last_three_price>0 ? "red" : item.last_three_price<0 ? "green" : "black"};">收:${item.last_three_price}%</span><span style="color:${item.last_three_high>0 ? "red" : item.last_three_high<0 ? "green" : "black"};">高:${item.last_three_high}%</span><span style="color:${item.last_three_low>0 ? "red" : item.last_three_low<0 ? "green" : "black"};">低:${item.last_three_low}%</span></div>
                      <div class="three-price"><span style="color:${item.last_four_price>0 ? "red" : item.last_four_price<0 ? "green" : "black"};">收:${item.last_four_price}%</span><span style="color:${item.last_four_high>0 ? "red" : item.last_four_high<0 ? "green" : "black"};">高:${item.last_four_high}%</span><span style="color:${item.last_four_low>0 ? "red" : item.last_four_low<0 ? "green" : "black"};">低:${item.last_four_low}%</span></div>
                      <div class="three-price"><span style="color:${item.last_five_price>0 ? "red" : item.last_five_price<0 ? "green" : "black"};">收:${item.last_five_price}%</span><span style="color:${item.last_five_high>0 ? "red" : item.last_five_high<0 ? "green" : "black"};">高:${item.last_five_high}%</span><span style="color:${item.last_five_low>0 ? "red" : item.last_five_low<0 ? "green" : "black"};">低:${item.last_five_low}%</span></div></div>`;
            })
            document.getElementsByClassName("list")[0].innerHTML = s;
            if (page === parseInt((data.total + pageSize -1) / pageSize)) {
                document.getElementById("next-page").disabled = 'true';
            }
        })
}

document.getElementById("pre-page").disabled = 'true';
getStockList();
