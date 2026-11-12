#include <cstdint>
#include <iostream>
#include <fstream>
#include <sstream>
#include <string>
#include <list>
#include <map>
#include <unordered_map>
#include <iterator>
#include <iomanip>
#include <filesystem>

struct OrderRecord
{
    std::int64_t order_id;
    char activity_type;
    char side;
    std::int64_t price;
    std::int64_t quantity;
    std::int64_t new_order_id;
    std::int64_t timestamp;
    std::int64_t event_index;
};
struct OrderRecordPosition
{
    char side;
    std::int64_t price;
    std::list<OrderRecord>::iterator position;
};
struct PriceLevel
{
    std::int64_t total_shares = 0;
    std::list<OrderRecord> orders;
};
struct Quote
{
    std::int64_t bid_size = 0;
    std::int64_t bid_price = 0;
    std::int64_t ask_size = 0;
    std::int64_t ask_price = 0;
    bool operator==(const Quote &o) const
    {
        return bid_price == o.bid_price && bid_size == o.bid_size &&
               ask_price == o.ask_price && ask_size == o.ask_size;
    }
    bool operator!=(const Quote &o) const { return !(*this == o); }
};

static std::map<std::int64_t, PriceLevel, std::greater<std::int64_t>> buySide;
static std::map<std::int64_t, PriceLevel> sellSide;
static std::unordered_map<std::int64_t, OrderRecordPosition> orderIDLookUp;

static Quote currentQuote()
{
    Quote q;
    if (!buySide.empty())
    {
        q.bid_price = buySide.begin()->first;
        q.bid_size = buySide.begin()->second.total_shares;
    }
    if (!sellSide.empty())
    {
        q.ask_price = sellSide.begin()->first;
        q.ask_size = sellSide.begin()->second.total_shares;
    }
    return q;
}

static void printOrderRecord(const OrderRecord &order)
{
    std::cout << order.order_id << ' ' << order.activity_type << ' ' << order.side << ' '
              << order.price << ' ' << order.quantity << ' ' << order.new_order_id << ' '
              << order.timestamp << ' ' << order.event_index << '\n';
}

// ITCH price (1/10,000 dollar) -> "276.9000"; empty side (0) -> ""
static void printPrice(std::ostream &out, std::int64_t price)
{
    if (price == 0)
        return;
    out << price / 10000 << '.' << std::setw(4) << std::setfill('0') << price % 10000
        << std::setfill(' ');
}

// One CSV row, same columns as parser/main.py's quotes.csv
static void printQuote(std::ostream &out, const std::string &symbol, const Quote &q, const OrderRecord &order)
{
    out << order.timestamp << ',' << order.event_index << ',' << symbol << ',';
    printPrice(out, q.bid_price);
    out << ',' << q.bid_size << ',';
    printPrice(out, q.ask_price);
    out << ',' << q.ask_size << ',' << order.activity_type << '\n';
}

// Opens output_binaries/quotes/quotes_<SYMBOL>.csv and writes the header row
static bool openQuoteFile(std::ofstream &out, const std::string &symbol)
{
    const std::filesystem::path dir = "output_binaries/quotes";
    std::filesystem::create_directories(dir);
    const std::filesystem::path path = dir / ("quotes_" + symbol + ".csv");
    out.open(path);
    if (!out.is_open())
    {
        std::cerr << "Could not open " << path << '\n';
        return false;
    }
    out << "timestamp_ns,source_event_index,symbol,bid_price,bid_size,ask_price,ask_size,event_type\n";
    std::cerr << "Writing quotes to " << path << '\n';
    return true;
}

static void ADD_ORDER(const OrderRecord &order)
{
    if (order.side == 'B')
    {
        if (!buySide.count(order.price))
        {
            std::list<OrderRecord> recordList;
            recordList.push_back(order);
            buySide[order.price].orders = recordList;
            buySide[order.price].total_shares += order.quantity;
        }
        else
        {
            buySide[order.price].orders.push_back(order);
            buySide[order.price].total_shares += order.quantity;
        }
        orderIDLookUp[order.order_id] = {
            order.side,
            order.price,
            std::prev(buySide[order.price].orders.end())};
    }
    else if (order.side == 'S')
    {
        if (!sellSide.count(order.price))
        {
            std::list<OrderRecord> recordList;
            recordList.push_back(order);
            sellSide[order.price].orders = recordList;
            sellSide[order.price].total_shares += order.quantity;
        }
        else
        {
            sellSide[order.price].orders.push_back(order);
            sellSide[order.price].total_shares += order.quantity;
        }
        orderIDLookUp[order.order_id] = {
            order.side,
            order.price,
            std::prev(sellSide[order.price].orders.end())};
    }
}
static void DELETE_ORDER(const OrderRecord &order)
{
    if (orderIDLookUp.count(order.order_id))
    {
        char side = orderIDLookUp[order.order_id].side;
        std::int64_t price = orderIDLookUp[order.order_id].price;
        auto &position = orderIDLookUp[order.order_id].position;
        if (side == 'B')
        {
            // remove from the buy side
            if (buySide.count(price))
            {
                auto &order_record = buySide[price];
                // remove
                order_record.total_shares -= position->quantity;
                order_record.orders.erase(position);
                // if the price level is empty

                if (order_record.orders.empty())
                {
                    buySide.erase(price);
                }
            }
            else
            {
                std::cerr << "The price level doesn't exists for REMOVAL";
                return;
            }
        }

        else if (side == 'S')
        {
            if (sellSide.count(price))
            {

                auto &order_record = sellSide[price];
                // remove
                order_record.total_shares -= position->quantity;
                order_record.orders.erase(position);
                // if the price level is empty

                if (order_record.orders.empty())
                {
                    sellSide.erase(price);
                }
            }
            else
            {
                std::cerr << "The price level doesn't exists for REMOVAL";
                return;
            }
        }
        orderIDLookUp.erase(order.order_id);
    }
    else
    {
        std::cerr << "NO ORDER ID FOUND FOR REMOVAL OF THE ORDER";
    }
}

static void CANCEL_ORDER(const OrderRecord &order)
{
    std::int64_t cancelQuanity = order.quantity;
    if (orderIDLookUp.count(order.order_id))
    {
        // get the side
        char side = orderIDLookUp[order.order_id].side;
        std::int64_t price = orderIDLookUp[order.order_id].price;
        auto &position = orderIDLookUp[order.order_id].position;
        if (side == 'B')
        {
            if (buySide.count(price))
            {
                position->quantity -= cancelQuanity;
                buySide[price].total_shares -= cancelQuanity;

                if (position->quantity == 0)
                {
                    DELETE_ORDER(order);
                }
            }
            else
            {
                std::cerr << "The price level doesn't exists for PARTIAL CANCELLATION";
            }
        }
        else if (side == 'S')
        {
            if (sellSide.count(price))
            {

                position->quantity -= cancelQuanity;
                sellSide[price].total_shares -= cancelQuanity;

                if (position->quantity == 0)
                {
                    DELETE_ORDER(order);
                }
            }
            else
            {
                std::cerr << "The price level doesn't exists for PARTIAL CANCELLATION";
            }
        }
    }
    else
    {
        std::cerr << "NO ORDER ID FOUND FOR PARTIAL CANCELLATION OF THE ORDER";
    }
}
static void UPDATE_ORDER(const OrderRecord &order)
{
    OrderRecord modified_order{};
    if (orderIDLookUp.count(order.order_id))
    {
        char modification_side = orderIDLookUp[order.order_id].side;
        modified_order.activity_type = order.activity_type;
        modified_order.side = modification_side;
        modified_order.price = order.price;
        modified_order.quantity = order.quantity;
        modified_order.order_id = order.new_order_id;

        DELETE_ORDER(order);
        ADD_ORDER(modified_order);
    }
    else
    {
        std::cout << "Cannot modify this order order id was not found" << '\n';
    }
}

int main(int argc, char *argv[])
{
    if (argc < 2)
    {
        std::cerr << "Usage: " << argv[0] << " SYMBOL\n";
        return 1;
    }
    const std::string symbol = argv[1];
    std::ofstream quoteFile;
    if (!openQuoteFile(quoteFile, symbol))
        return 1;

    std::string line;
    int count = 0;

    while (std::getline(std::cin, line))
    {
        std::istringstream ss(line);
        OrderRecord order{};
        ss >> order.order_id >> order.activity_type >> order.side >> order.price >> order.quantity >> order.new_order_id >> order.timestamp >> order.event_index;
        Quote before = currentQuote();
        switch (order.activity_type)
        {
        case 'A':
            ADD_ORDER(order);
            break;
        case 'F':
            ADD_ORDER(order);
            break;
        case 'D':
            DELETE_ORDER(order);
            break;
        case 'U':
            UPDATE_ORDER(order);
            break;
        case 'X':
            CANCEL_ORDER(order);
            break;
        case 'E':
            CANCEL_ORDER(order);
            break;
        case 'C':
            CANCEL_ORDER(order);
            break;
        default:
            std::cerr << "INVALID MESSAGE ACTIVITY TYPE " << order.activity_type << "\n";
            break;
        }
        Quote after = currentQuote();
        if (before != after)
        {
            printQuote(quoteFile, symbol, after, order);
        }
        count++;
    }
    std::cerr << "Processed " << count << " Orders\n";
    return 0;
}