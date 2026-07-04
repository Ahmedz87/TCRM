//+------------------------------------------------------------------+
//|                                        Commission reports plugin |
//|                   Copyright 2001-2014, MetaQuotes Software Corp. |
//|                                        http://www.metaquotes.net |
//+------------------------------------------------------------------+
#pragma once

//+------------------------------------------------------------------+
//|                                                                  |
//+------------------------------------------------------------------+
class CCommissionReport : public CReport
  {
public:
                     CCommissionReport(CReport *next,LPCSTR name);
   //--- генерация отчетов
   int               GenerateHTML(const ReportParams *params);
   int               GenerateCSV(const ReportParams *params);

private:
   static int        UsersSortByGroup(const void *param1,const void *param2);
   static int        UsersSearchByGroup(const void *param1,const void *param2);
   static int        TradesSortByLogin(const void *param1,const void *param2);
   static int        TradesSearchByLogin(const void *param1,const void *param2);
  };
//+------------------------------------------------------------------+
