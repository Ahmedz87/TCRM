//+------------------------------------------------------------------+
//|                                                   Reports plugin |
//|                   Copyright 2001-2014, MetaQuotes Software Corp. |
//|                                        http://www.metaquotes.net |
//+------------------------------------------------------------------+
#pragma once
//---
#define REPORTS_API __declspec(dllexport)
//--- reports api version
#define REPORTS_VERSION       (400)
//+------------------------------------------------------------------+
//| Report types mask                                                |
//+------------------------------------------------------------------+
enum
  {
   REPORT_TYPE_RAW    =0x01,                    // raw report
//---
   REPORT_TYPE_ONLINE =0x02,                    // online users report
   REPORT_TYPE_USERS  =0x04,                    // accounts report
   REPORT_TYPE_ORDERS =0x08,                    // open orders report
   REPORT_TYPE_REPORTS=0x10,                    // closed trades report
   REPORT_TYPE_HISTORY=0x20,                    // history report
   REPORT_TYPE_JOURNAL=0x40                     // server journal
  };
//+------------------------------------------------------------------+
//| Security configurations                                          |
//+------------------------------------------------------------------+
//| Security sessions configurations                                 |
//+------------------------------------------------------------------+
struct ConSession
  {
   short             open_hour,open_min;        // session open  time: hour & minute
   short             close_hour,close_min;      // session close time: hour & minute
   int               open,close;                // internal data
   short             align[7];                  // internal data
  };
//---
struct ConSessions
  {
   //---
   ConSession        quote[3];                  // quote sessions
   ConSession        trade[3];                  // trade sessions
   //---
   int               quote_overnight;           // internal data
   int               trade_overnight;           // internal data
   int               reserved[2];               // reserved
  };
//+------------------------------------------------------------------+
//| Security configuration                                           |
//+------------------------------------------------------------------+
#define MAX_SYMBOLS 1024
//---
struct ConSymbol
  {
   //--- common settings
   char              symbol[12];                // name
   char              description[64];           // description
   char              source[12];                // synonym
   char              currency[12];              // currency
   int               type;                      // security group (see ConSymbolGroup)
   int               digits;                    // security precision
   int               trade;                     // trade mode
   //--- external settings
   COLORREF          background_color;          // background color
   int               count;                     // symbols index
   int               count_original;            // symbols index in market watch
   int               external_unused[7];
   //--- sessions
   int               realtime;                  // allow real time quotes
   time_t            starting;                  // trades starting date (UNIX time)
   time_t            expiration;                // trades end date      (UNIX time)
   ConSessions       sessions[7];               // quote & trade sessions
   //--- profits
   int               profit_mode;               // profit calculation mode
   int               profit_reserved;           // reserved
   //--- filtration
   int               filter;                    // (less than 1 means filtering disabled)
   int               filter_counter;            // filtration parameter
   double            filter_limit;              // max. permissible deviation from last quote (percents)
   double            filter_reserved;           // reserved
   int               logging;                   // enable to log quotes
   //--- spread & swaps
   int               spread;                    // spread
   int               spread_balance;            // spread balance
   int               exemode;                   // execution mode
   int               swap_enable;               // enable swaps
   int               swap_type;                 // swap type
   double            swap_long,swap_short;      // swaps values for long & short postions
   int               swap_rollover3days;        // triple rollover day-0-Monday,1-Tuesday...4-Friday
   double            contract_size;             // contract size
   double            tick_value;                // one tick value
   double            tick_size;                 // one tick size
   int               stops_level;               // stops deviation value
   //---
   int               gtc_pendings;              // GTC mode { ORDERS_DAILY, ORDERS_GTC, ORDERS_DAILY_NO_STOPS }
   //--- margin calculation
   int               margin_mode;               // margin calculation mode
   double            margin_initial;            // initial margin
   double            margin_maintenance;        // margin maintenance
   double            margin_hedged;             // hadget margin
   double            margin_divider;            // margin divider
   //--- calclulated variables (internal data)
   double            point;                     // point size-(1/(10^digits)
   double            multiply;                  // multiply 10^digits
   double            bid_tickvalue;             // tickvalue for bid
   double            ask_tickvalue;             // tickvalue for ask
   //---
   int               long_only;                 // allow only BUY positions
   int               instant_max_volume;        // max. volume for Instant Execution
   //---
   char              margin_currency[12];       // currency of margin requirments
   int               freeze_level;              // modification freeze level
   int               margin_hedged_strong;      // strong hedged margin mode
   time_t            value_date;                // value date
   int               quotes_delay;              // quotes delay after session start
   //---
   int               unused[23];                // reserved
  };
//+------------------------------------------------------------------+
//| Symbols enumeration                                              |
//+------------------------------------------------------------------+
//--- symbol execution mode
enum { EXE_REQUEST,EXE_INSTANT,EXE_MARKET };
//--- trade mode
enum { TRADE_NO,TRADE_CLOSE,TRADE_FULL };
//--- swap type
enum { SWAP_BY_POINTS,SWAP_BY_DOLLARS,SWAP_BY_INTEREST,SWAP_BY_MARGIN_CURRENCY };
//--- profit calculation mode
enum { PROFIT_CALC_FOREX,PROFIT_CALC_CFD,PROFIT_CALC_FUTURES };
//--- margin calculation mode
enum { MARGIN_CALC_FOREX,MARGIN_CALC_CFD,MARGIN_CALC_FUTURES,MARGIN_CALC_CFDINDEX,MARGIN_CALC_CFDLEVERAGE };
//--- GTC mode
enum { ORDERS_DAILY, ORDERS_GTC, ORDERS_DAILY_NO_STOPS };
//+------------------------------------------------------------------+
//| Groups configuration                                             |
//+------------------------------------------------------------------+
//| Security group configuration for client group                    |
//+------------------------------------------------------------------+
#define MAX_SEC_GROUPS       (32)
#define MAX_SEC_GROPS_MARGIN (128)
//---
struct ConGroupSec
  {
   int               show,trade;                // enable show and trade for this group of securites
   int               execution;                 // dealing mode-EXECUTION_MANUAL,EXECUTION_AUTO,EXECUTION_ACTIVITY
   //--- comission settings
   double            comm_base;                 // standart commission
   int               comm_type;                 // commission type-COMM_TYPE_MONEY,COMM_TYPE_PIPS,COMM_TYPE_PERCENT
   int               comm_lots;                 // commission lots mode-COMMISSION_PER_LOT,COMMISSION_PER_DEAL
   double            comm_agent;                // agent commission
   int               comm_agent_type;           // agent commission mode-COMM_TYPE_MONEY, COMM_TYPE_PIPS
   //---
   int               spread_diff;               // spread difference in compare with default security spread
   //---
   int               lot_min,lot_max;           // allowed minimal and maximal lot values
   int               lot_step;                  // allowed step value (10 lot-1000, 1 lot-100, 0.1 lot-10)
   int               ie_deviation;              // maximum price deviation in Instant Execution mode
   int               confirmation;              // use confirmation in Request mode
   int               trade_rights;              // clients trade rights-bit mask see TRADE_DENY_NONE,TRADE_DENY_CLOSEBY,TRADE_DENY_MUCLOSEBY
   int               coverage_mode;             // resend request to the dealer when client uses deviation
   int               autocloseout_mode;         // auto close-out method { CLOSE_OUT_NONE, CLOSE_OUT_HIHI, CLOSE_OUT_LOLO, CLOSE_OUT_HILO, CLOSE_OUT_LOHI, CLOSE_OUT_LOHI, CLOSE_OUT_FIFO, CLOSE_OUT_LIFO, CLOSE_OUT_INTRDAY_FIFO }
   double            comm_tax;                  // commission taxes
   int               comm_agent_lots;           // agent commission per lot/per deal { COMMISSION_PER_LOT,COMMISSION_PER_DEAL }
   int               reserved[4];               // reserved
  };
//+------------------------------------------------------------------+
//| Special securities configurations for client group               |
//+------------------------------------------------------------------+
struct ConGroupMargin
  {
   char              symbol[12];                // security
   double            swap_long,swap_short;      // tickvalue for bid & ask
   double            margin_divider;            // margin divider
   int               reserved[7];               // reserved
  };
//--- dealing mode
enum { EXECUTION_MANUAL, EXECUTION_AUTO, EXECUTION_ACTIVITY };
//--- commission type
enum { COMM_TYPE_MONEY, COMM_TYPE_PIPS, COMM_TYPE_PERCENT };
//--- comission lots mode
enum { COMMISSION_PER_LOT, COMMISSION_PER_DEAL };
//--- clients trade rights
enum { TRADE_DENY_NONE=0, TRADE_DENY_CLOSEBY=1, TRADE_DENY_MUCLOSEBY=2 };
//--- auto close-out method
enum { CLOSE_OUT_NONE, CLOSE_OUT_HIHI, CLOSE_OUT_LOLO, CLOSE_OUT_HILO, CLOSE_OUT_LOHI, CLOSE_OUT_FIFO, CLOSE_OUT_LIFO, CLOSE_OUT_INTRDAY_FIFO };
//+------------------------------------------------------------------+
//| Client group configuration                                       |
//+------------------------------------------------------------------+
struct ConGroup
  {
   //--- common settings
   char              group[16];                 // group name
   int               enable;                    // enable group
   int               timeout;                   // trade confirmation timeout (seconds)
   int               adv_security;              // enable advanced security
   //--- statements
   char              company[128];              // company name
   char              signature[128];            // statements signature
   char              support_page[128];         // company support page
   char              smtp_server[64];           // statements SMTP server
   char              smtp_login[32];            // statements SMTP login
   char              smtp_password[32];         // statements SMTP password
   char              support_email[64];         // support email
   char              templates[32];             // path to directory with custom templates
   int               copies;                    // copy statements on support email
   int               reports;                   // enable statements
   //--- default settings
   int               default_leverage;          // default leverage (user don't specify leverage himself)
   double            default_deposit;           // default deposit  (user don't specify balance  himself)
   //--- securities
   int               maxsecurities;             // maximum simultaneous securities
   ConGroupSec       secgroups[MAX_SEC_GROUPS]; // security group settings
   ConGroupMargin    secmargins[MAX_SEC_GROPS_MARGIN]; // special securities settings
   int               secmargins_total;          // count of special securities settings
   //--- margin & interest
   char              currency[12];              // deposit currency
   double            credit;                    // virtual credit
   int               margin_call;               // margin call level (percents)
   int               margin_mode;               // margin mode-MARGIN_DONT_USE,MARGIN_USE_ALL,MARGIN_USE_PROFIT,MARGIN_USE_LOSS
   int               margin_stopout;            // stop out level
   double            interestrate;              // annual interest rate (percents)
   int               use_swap;                  // use rollovers & interestrate
   //--- rights
   int               news;                      // news mode
   int               rights;                    // rights bit mask-ALLOW_FLAG_EMAIL
   int               check_ie_prices;           // check IE prices on requests
   int               maxpositions;              // maximum orders and open positions
   int               unused_rights[6];          // internal data
   char              securities_hash[16];       // internal data
   //---
   int               margin_type;               // margin controlling type { MARGIN_TYPE_PERCENT,  MARGIN_TYPE_CURRENCY }
   int               archive_period;            // inactivity period (in months) to move accounts in the archive
   int               archive_max_balance;       // maximal balance of accounts to move in the archive
   int               stopout_skip_hedged;       // skip fully hedged accounts when checking for stopout
   //---
   int               reserved[27];
  };
//--- margin calculation mode
enum { MARGIN_MODE_DONT_USE,MARGIN_MODE_USE_ALL,MARGIN_MODE_USE_PROFIT,MARGIN_MODE_USE_LOSS };
//--- margin controlling type
enum { MARGIN_TYPE_PERCENT, MARGIN_TYPE_CURRENCY };
//--- news mode-no news, only topics, full news (topic+body)
enum { NEWS_NO, NEWS_TOPICS, NEWS_FULL  };
//--- group rights
enum { ALLOW_FLAG_EMAIL=1, ALLOW_FLAG_TRAILING=2, ALLOW_FLAG_ADVISOR=4, ALLOW_FLAG_EXPIRATION=8 };
//+------------------------------------------------------------------+
//| Database records                                                 |
//+------------------------------------------------------------------+
//| User Record                                                      |
//+------------------------------------------------------------------+
#define PUBLIC_KEY_SIZE    272                  // RSA key size // (((1024+64)/32)*4*2)
#define USER_COLOR_NONE    (0xFF000000)         // default user color
//---
struct UserRecord
  {
   //--- common settings
   int               login;                      // login
   char              group[16];                  // group
   char              password[16];               // password
   //--- access flags
   int               enable;                     // enable
   int               enable_change_password;     // allow to change password
   int               enable_read_only;           // allow to open/positions (TRUE-may not trade)
   int               enable_reserved[3];         // for future use
   //---
   char              password_investor[16];      // read-only mode password
   char              password_phone[32];         // phone password
   char              name[128];                  // name
   char              country[32];                // country
   char              city[32];                   // city
   char              state[32];                  // state
   char              zipcode[16];                // zipcode
   char              address[128];               // address
   char              phone[32];                  // phone
   char              email[48];                  // email
   char              comment[64];                // comment
   char              id[32];                     // SSN (IRD)
   char              status[16];                 // status
   time_t            regdate;                    // registration date
   time_t            lastdate;                   // last coonection time
   //--- trade settings
   int               leverage;                   // leverage
   int               agent_account;              // agent account
   int               reserved[2];                // for future use
   //---            торговые данные
   double            balance;                    // balance
   double            prevmonthbalance;           // previous month balance
   double            prevbalance;                // previous day balance
   double            credit;                     // credit
   double            interestrate;               // accumulated interest rate
   double            taxes;                      // taxes
   double            reserved2[4];               // for future use
   //---
   char              publickey[PUBLIC_KEY_SIZE]; // public key
   int               send_reports;               // enable send reports by email
   int               balance_status;             // internal use
   COLORREF          user_color;                 // color got to client (used by MT Manager)
   //---
   char              unused[40];                 // for future use
   char              api_data[16];               // for API usage
  };
//+------------------------------------------------------------------+
//| Online User Record                                               |
//+------------------------------------------------------------------+
struct OnlineUserRecord
  {
   int               login;                     // login
   char              name[128];                 // name
   char              group[16];                 // group
   char              email[48];                 // email
   char              country[32];               // country
   char              comment[64];               // comment
   double            balance;                   // balance
   double            credit;                    // credit
   char              ip[16];                    // IP address
   int               counter;                   // connections counter
  };
//+------------------------------------------------------------------+
//| Trade Record                                                     |
//+------------------------------------------------------------------+
#pragma pack(push,1)
struct TradeRecord
  {
   int               order;                     // order ticket
   int               login;                     // owner's login
   char              symbol[12];                // security
   int               digits;                    // security precision
   int               cmd;                       // trade command
   int               volume;                    // volume
   //---
   time_t            open_time;                 // open time
   int               open_reserv;               // reserved
   double            open_price;                // open price
   double            sl,tp;                     // stop loss & take profit
   time_t            close_time;                // close time
   int               gw_volume;                 // gateway order volume
   time_t            expiration;                // pending order's expiration time
   int               conv_reserv;               // reserved
   double            conv_rates[2];             // convertation rates from profit currency to group deposit currency
   // (first element-for open time, second element-for close time)
   double            commission;                // commission
   double            commission_agent;          // agent commission
   double            storage;                   // order swaps
   double            close_price;               // close price
   double            profit;                    // profit
   double            taxes;                     // taxes
   int               magic;                     // special value used by client experts
   char              comment[32];               // comment
   int               gw_order;                  // gateway order
   int               activation;                // used by MT Manager
   short             gw_open_price;             // gateway order open price shift
   short             gw_close_price;            // gateway order close price shift
   double            margin_rate;               // margin convertation rate (rate of convertation from margin currency to deposit one)
   time_t            timestamp;                 // timestamp
   int               api_data[4];               // api data
   TradeRecord      *next;                      // internal data
  };
#pragma pack(pop)
//--- trade commands
enum { OP_BUY=0,OP_SELL,OP_BUY_LIMIT,OP_SELL_LIMIT,OP_BUY_STOP,OP_SELL_STOP,OP_BALANCE,OP_CREDIT };
//+------------------------------------------------------------------+
//| Margin level of the user                                         |
//+------------------------------------------------------------------+
struct MarginLevel
  {
   int               login;                     // user login
   char              group[16];                 // user group
   int               leverage;                  // user leverage
   int               updated;                   // (internal)
   double            balance;                   // balance+credit
   double            equity;                    // equity
   __int64           volume;                    // lots
   double            margin;                    // margin requirements
   double            margin_free;               // free margin
   double            margin_level;              // margin level
   int               margin_type;               // margin controlling type (percent/currency)
   int               level_type;                // level type(ok/margincall/stopout)
   //--- stopout data
   double            so_level;                  // margin level at last stopout
   double            so_equity;                 // equity on stotout
   double            so_margin;                 // margin at stopout
  };
//--- margin level type
enum { MARGINLEVEL_OK=0, MARGINLEVEL_MARGINCALL, MARGINLEVEL_STOPOUT };
//+------------------------------------------------------------------+
//| Daily report                                                     |
//+------------------------------------------------------------------+
struct DailyReport
  {
   int               login;                     // login
   time_t            ctm;                       // time
   char              group[16];                 // group
   char              bank[64];                  // bank
   double            balance_prev;              // previous balance
   double            balance;                   // balance
   double            deposit;                   // deposit
   double            credit;                    // credit
   double            profit_closed;             // closed profit/loss
   double            profit;                    // floating profit/loss
   double            equity;                    // equity
   double            margin;                    // used margin
   double            margin_free;               // free margin
   //---
   int               next;                      // (internal)
   int               reserved[3];               // reserved
  };
//+------------------------------------------------------------------+
//| Server journal record                                            |
//+------------------------------------------------------------------+
struct ServerLog
  {
   int               code;                      // code
   char              time[24];                  // time
   char              ip[256];                   // ip
   char              message[512];              // message
  };
//--- log record codes
  enum { CmdOK,           // ok
   CmdTrade,        // trades
   CmdLogin,        // logins
   CmdWarn,         // warnings
   CmdErr,          // errors
   CmdAtt,          // attention error
   CmdDay=CmdOK-1
  };
//+------------------------------------------------------------------+
//|                                                                  |
//+------------------------------------------------------------------+
//| Callback function defined by the host MT Manager terminal.       |
//| Should be called periodically by report plugin                   |
//| during report generation to indicate generation progress and     |
//| to check generation cancellation.                                |
//|   Parameters: (UINT custom,int current_step,int total_steps)     |
//|   Returns: 0-continue generation; not 0-cancel generation        |
//+------------------------------------------------------------------+
typedef int (*REP_PROGRESS_FUNC)(UINT,int,int);
//+------------------------------------------------------------------+
//| Set of users for report                                          |
//+------------------------------------------------------------------+
struct ReportGroupBrief
  {
   char              name[32];                  // name
   time_t            from,to;                   // reporting period
   int               total;                     // total users in the set
  };
//+------------------------------------------------------------------+
//| Single report definition                                         |
//+------------------------------------------------------------------+
struct RepGeneratorInfo
  {
   int               id_internal;               // internal (dll) report id
   char              name[64];                  // report name for MT Manager menu
   int               reserved;                  // reserved
   int               type;                      // report type
   char              formats[128];              // supported save file types
   char              def_ext[6];                // default file extension
   int               def_index;                 // default save file type
  };
//+------------------------------------------------------------------+
//| Report parameters and source data                                |
//+------------------------------------------------------------------+
struct ReportParams
  {
   int               id_internal;               // internal (dll) report id
   char              name[64];                  // report name for MT Manager menu
   int               reserved;                  // reserved
   int               type;                      // report type
   char              filepath[256];             // report save path
   int               extension;                 // report extension
   //--- данные
   TradeRecord      *trades;                    // trades
   int               trades_total;              // total trades
   UserRecord       *users;                     // users
   int               users_total;               // total users
   ConGroup         *user_groups;               // groups
   int               user_groups_total;         // total groups
   ConSymbol        *symbols;                   // symbols
   int               symbols_total;             // total symbols
   void             *buffer;                    // addition custom data
   size_t            buffer_size;               // size of custion data in bytes
   ReportGroupBrief  group;                     // set of users for report
   int              *group_logins;              // user logins
   //---
   REP_PROGRESS_FUNC fn_progress;               // progress/cancel callback
   UINT              custom;                    // callback first parameter
  };
//+------------------------------------------------------------------+
//|                                                                  |
//+------------------------------------------------------------------+
const UserRecord    *UserRecordGet(const ReportParams *params,int login);
const ConSymbol     *SymbolGet(const ReportParams *params,LPCSTR symbol);
const ConGroup      *GroupGet(const ReportParams *params,LPCSTR group);
//---
LPCSTR               GetCmd(const int cmd);
double               Decimals(const int digits);
LPSTR                ToSym(char *pricebuf,const int len,const double price,int digits);
LPSTR                ToSymExt(char *psz,const double val,int digits,int more=3);
LPSTR                ToMoney(const double val,int digits,char *psz,const int maxchars);
void                 ExportHeader(FILE *out,LPCSTR title);
double               NormalizeDouble(const double val,int digits);
LPCSTR               FormatDateTime(time_t ctm,LPSTR sz,int maxchars,BOOL bUseTime=TRUE,BOOL bUseSec=FALSE);
//+------------------------------------------------------------------+
//|                                                                  |
//+------------------------------------------------------------------+
