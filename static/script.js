const tablinks = document.getElementsByClassName("tablink");
for (const link of tablinks) {
    link.addEventListener("click", function() {openTab(link.getAttribute("tab"));})
    if (link.classList.contains("default")) {
        openTab(link.getAttribute("tab"));
    }
}

function openTab(tabName) {
    tabContent = document.getElementById(tabName);

    for (const tab of document.getElementsByClassName("tabcontent")) {
        if (tabContent.getAttribute("tabbar") != tab.getAttribute("tabbar"))
            continue;
        tab.classList.remove("active");
    }
    tabContent.classList.add("active");
    for (const link of document.getElementsByClassName("tablink")) {
        if (tabContent.getAttribute("tabbar") != link.parentElement.id)
            continue;
        if (link.getAttribute("tab") == tabName)
            link.classList.add("active");
        else
            link.classList.remove("active");
    }
}