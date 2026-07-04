//+------------------------------------------------------------------+
//|                                        Commission reports plugin |
//|                   Copyright 2001-2014, MetaQuotes Software Corp. |
//|                                        http://www.metaquotes.net |
//+------------------------------------------------------------------+
#pragma once

//+------------------------------------------------------------------+
//| Описание комиссия                                                |
//+------------------------------------------------------------------+
struct Commission
  {
   char              group_symbol[128];   // имя группы и символ
   double            commission;          // значение комиссия
  };
//+------------------------------------------------------------------+
//|                                                                  |
//+------------------------------------------------------------------+
class CConfiguration
  {
private:
   Commission       *m_commissions;       // комиссии
   int               m_commissions_total; // количество комиссий

public:
                     CConfiguration();
                    ~CConfiguration();
   //---
   int               Reload(ConGroup *groups,const int groups_total,
                            ConSymbol *symbols,const int symbols_total);
   //--- получения размера коммисии для группы и опредленного символа
   double            GetCommission(const char *group,const char *symbol);
  };
//---
extern CConfiguration ExtConfig;
//+------------------------------------------------------------------+
