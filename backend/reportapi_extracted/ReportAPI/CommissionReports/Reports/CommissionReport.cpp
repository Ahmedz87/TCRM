//+------------------------------------------------------------------+
//|                                        Commission reports plugin |
//|                   Copyright 2001-2014, MetaQuotes Software Corp. |
//|                                        http://www.metaquotes.net |
//+------------------------------------------------------------------+
#include "..\stdafx.h"
#include "CommissionReport.h"
//+------------------------------------------------------------------+
//|                                                                  |
//+------------------------------------------------------------------+
CCommissionReport::CCommissionReport(CReport *next,LPCSTR name) :
   CReport(next,name,"HTML format (*.htm)|*.htm|")
  {
//--- скажем что это репорт по закрытым сделкам
   m_info.type=REPORT_TYPE_REPORTS;
//---
  }
//+------------------------------------------------------------------+
//|                                                                  |
//+------------------------------------------------------------------+
int CCommissionReport::GenerateHTML(const ReportParams *params)
  {
   char         tmp[1024];
   double       lots,symbol_commission,commission,summary_lots,summary_commission,pip_cost;
   UserRecord  *start_user,*user;
   TradeRecord *trade;
   ConGroup    *group;
   ConSymbol   *symbol;
   int          i=0,skip_flag,group_header;
//--- проверки
   if(params==NULL || params->trades==NULL || params->trades_total<0 ||
      params->user_groups==NULL || params->user_groups_total<0 ||
      params->users      ==NULL || params->users_total      <0 ||
      params->symbols    ==NULL || params->symbols_total    <0) return(FALSE);
//--- перезагрузим параметры
   if(ExtConfig.Reload(params->user_groups,params->user_groups_total,
      params->symbols,params->symbols_total)==FALSE) return(FALSE);
//--- откроем файл
   if(m_file!=NULL) fclose(m_file);
   if((m_file=fopen(params->filepath,"wt"))==NULL) return(FALSE);
//--- начинаем генерацию: пишем шапки
   WriteHeader(m_info.name);
   fprintf(m_file,"<style>\n"
                  ".money { mso-number-format:\\#\\,\\#\\#0\\.00; }\n"
                  ".lots  { mso-number-format:0\\.00; }\n"
                  ".dt    { mso-number-format:\"yyyy\\.mm\\.dd hh\\:mm\"; }\n"
                  ".pt0   { mso-number-format:0; }\n"
                  ".pt1   { mso-number-format:0\\.0; }\n"
                  ".pt2   { mso-number-format:0\\.00; }\n"
                  ".pt3   { mso-number-format:0\\.000; }\n"
                  ".pt4   { mso-number-format:0\\.0000; }\n"
                  ".pt5   { mso-number-format:0\\.00000; }\n"
                  ".pt6   { mso-number-format:0\\.000000; }\n"
                  ".pt7   { mso-number-format:0\\.0000000; }\n"
                  ".pt8   { mso-number-format:0\\.00000000; }\n"
                  "</style>\n");
//--- пишем заголовок
   fprintf(m_file,"<div align=center>\n");
   fprintf(m_file,"<table cellspacing=1 cellpadding=2 border=0 width=\"100%%\">\n");
   fprintf(m_file,"<tr><td><font size=2><b>Commission Report</b> for '%s'",params->group.name);
   FormatDateTime(params->group.from,tmp,sizeof(tmp)-1,FALSE);
   fprintf(m_file," from %s",tmp);
   FormatDateTime(params->group.to-1,tmp,sizeof(tmp)-1,FALSE);
   fprintf(m_file," to %s",tmp);
   fprintf(m_file,"</font></td></tr>\n");
//--- отсортируем юзверей по группам
   if(params->users_total>0)
      qsort(params->users,params->users_total,sizeof(UserRecord),UsersSortByGroup);
//--- отсортируем трейды по логинам
   if(params->trades_total>0)
      qsort(params->trades,params->trades_total,sizeof(TradeRecord),TradesSortByLogin);
//--- начинаем ходить по группам
   for(group=params->user_groups;group<params->user_groups+params->user_groups_total;group++)
     {
      //--- занулим все для группы
      summary_lots=summary_commission=0;
      //--- говорим что шапку для группы не сделали (сделаем ее по первому нужному символу)
      group_header=FALSE;
      //--- найдем чуваков
      if((start_user=(UserRecord *)bsearch(group->group,params->users,
            params->users_total,sizeof(UserRecord),UsersSearchByGroup))!=NULL)
        {
         i=0;
         //--- откатимся до первого юзверя
         while(start_user>=params->users && strcmp(start_user->group,group->group)==0) start_user--;
         start_user++;
         //--- начинаем ходить по символам
         for(symbol=params->symbols;symbol<params->symbols+params->symbols_total;symbol++)
           {
            //--- занулим все для символа
            lots=commission=pip_cost=0;
            //--- получим комиссию по символу
            symbol_commission=ExtConfig.GetCommission(group->group,symbol->symbol);
            //--- выставим флаг того что не одну сделку не пропустили
            skip_flag=FALSE;
            //--- теперь ходим по зверям
            for(user=start_user;user<params->users+params->users_total && strcmp(user->group,group->group)==0;user++)
              {
               //--- найдем трейды для юзверя
               if((trade=(TradeRecord *)bsearch(&user->login,params->trades,
                  params->trades_total,sizeof(TradeRecord),TradesSearchByLogin))==NULL) continue;
               //--- откатился до первого трейда
               while(trade>=params->trades && trade->login==user->login) trade--;
               trade++;
               //--- теперь тупо бегаем по трейдам собирая данные
               for(;trade<params->trades+params->trades_total && trade->login==user->login;trade++)
                  if((trade->cmd==OP_BUY || trade->cmd==OP_SELL) && trade->close_time!=0 && strcmp(trade->symbol,symbol->symbol)==0)
                    {
                     //--- суммируем для символа лоты
                     lots=NormalizeDouble(lots+trade->volume/100.0,2);
                     //--- перевычислим стоимость пипса если есть возможность
                     if(trade->close_price-trade->open_price!=0 && trade->profit!=0)
                       {
                        //--- вычисляем стоимость пипса
                        pip_cost=fabs(trade->profit/
                           ((trade->close_price-trade->open_price)/(symbol->point)))*(100./trade->volume);
                        //--- суммируем комиссии
                        commission=NormalizeDouble(commission+symbol_commission*(trade->volume/100.0)*pip_cost,2);
                       }
                     else skip_flag=TRUE; // ага на чувака нет данных, придется пересчитать потом еще раз
                    }
              }
            //--- теперь глянем требуется ли нам перерасчет
            if(skip_flag==TRUE && pip_cost!=0)
              {
               //--- опять бегаем по юзерам
               for(user=start_user;user<params->users+params->users_total && strcmp(user->group,group->group)==0;user++)
                 {
                  //--- найдем трейды для юзверя
                  if((trade=(TradeRecord *)bsearch(&user->login,params->trades,
                     params->trades_total,sizeof(TradeRecord),TradesSearchByLogin))==NULL) continue;
                  //--- откатился до первого трейда
                  while(trade>=params->trades && trade->login==user->login) trade--;
                  trade++;
                  //--- теперь тупо бегаем по трейдам и пересчитываем пропущенные
                  for(;trade<params->trades+params->trades_total && trade->login==user->login;trade++)
                     if((trade->cmd==OP_BUY || trade->cmd==OP_SELL) && trade->close_time!=0 && strcmp(trade->symbol,symbol->symbol)==0)
                        if(trade->close_price-trade->open_price==0 || trade->profit==0)
                           commission=NormalizeDouble(commission+symbol_commission*(trade->volume/100.0)*pip_cost,2);
                 }
              }
            //--- добавим в итог по группе
            summary_lots      =NormalizeDouble(summary_lots+lots,2);
            summary_commission=NormalizeDouble(summary_commission+commission,2);
            //--- обновим прогресс, заодно глянем может нас тормознули
            if(params->fn_progress!=NULL)
               if(params->fn_progress(params->custom,(group-params->user_groups)*params->symbols_total+(symbol-params->symbols),
                  params->user_groups_total*params->symbols_total)!=0)
                 {
                  fclose(m_file);
                  return(FALSE);
                 }
            //--- если ничего нет то не выводим ничего
            if(lots==0 || commission==0) continue;
            //--- так если шапки еще нет, сделаем ее
            if(group_header==FALSE)
              {
               //--- выводим название группы и создаем внутренню таблицу для символов
               fprintf(m_file,"<tr><td></td><tr>");
               fprintf(m_file,"<tr><td><b>%s</b></td><tr>",group->group);
               fprintf(m_file,"<tr><td><table cellspacing=1 cellpadding=2 border=0 width=\"100%%\">\n");
               //--- сделаем заголовки для внутренней таблицы
               fprintf(m_file,"<tr bgcolor=\"#c0c0c0\">");
               fprintf(m_file,"<td width=\"55%%\">Symbol</td>");
               fprintf(m_file,"<td width=\"15%%\" align=right>Lots</td>");
               fprintf(m_file,"<td width=\"15%%\" align=right>Commission</td>");
               fprintf(m_file,"<td width=\"15%%\">Currency</td></tr>\n");
               //--- шапка у нас есть
               group_header=TRUE;
              }
            //--- выводим информацию по символу
            if(i++&1) fprintf(m_file,"<tr bgcolor=\"#e0e0e0\">");
            else      fprintf(m_file,"<tr>");
            //---
            fprintf(m_file,"<td>%s</td>",                               symbol->symbol);
            fprintf(m_file,"<td align=right class=lots>%.2f</td>",      lots);
            fprintf(m_file,"<td align=right class=money nowrap>%s</td>",ToMoney(commission,2,tmp,sizeof(tmp)-1));
            fprintf(m_file,"<td>%s</td></tr>\n",                        group->currency);
           }
         //--- если мы сделали шапку, то значит что-то есть и надо сделать итог
         if(group_header!=FALSE)
           {
            //--- выводим total
            if(i++&1) fprintf(m_file,"<tr bgcolor=\"#e0e0e0\">");
            else      fprintf(m_file,"<tr>");
            fprintf(m_file,"<td colspan=4><b>Total:</b></td></tr>\n");
            //--- выводим сам итог и закроем внутренню таблицу
            if(i++&1) fprintf(m_file,"<tr bgcolor=\"#e0e0e0\">");
            else      fprintf(m_file,"<tr>");
            fprintf(m_file,"<td></td>");
            fprintf(m_file,"<td align=right class=lots>%.2f</td>",      summary_lots);
            fprintf(m_file,"<td align=right class=money nowrap>%s</td>",ToMoney(summary_commission,2,tmp,sizeof(tmp)-1));
            fprintf(m_file,"<td>%s</td></tr>\n",                        group->currency);
            fprintf(m_file,"</table></td></tr>\n");
           }
        }
     }
//--- заканчиваем все
   fprintf(m_file,"</table></body></html>\n");
   fclose(m_file);
//---
   return(TRUE);
  }
//+------------------------------------------------------------------+
//|                                                                  |
//+------------------------------------------------------------------+
int CCommissionReport::GenerateCSV(const ReportParams *params)
  {
//--- типа такой тип отчета мы не поддерживаем
   return(FALSE);
  }
//+------------------------------------------------------------------+
//|                                                                  |
//+------------------------------------------------------------------+
int CCommissionReport::UsersSortByGroup(const void *param1,const void *param2)
  {
   return strcmp(((UserRecord *)param1)->group,((UserRecord *)param2)->group);
  }
//+------------------------------------------------------------------+
//|                                                                  |
//+------------------------------------------------------------------+
int CCommissionReport::TradesSortByLogin(const void *param1,const void *param2)
  {
   return(((TradeRecord *)param1)->login-((TradeRecord *)param2)->login);
  }
//+------------------------------------------------------------------+
//|                                                                  |
//+------------------------------------------------------------------+
int CCommissionReport::UsersSearchByGroup(const void *param1,const void *param2)
  {
   return strcmp((char *)param1,((UserRecord *)param2)->group);
  }
//+------------------------------------------------------------------+
//|                                                                  |
//+------------------------------------------------------------------+
int CCommissionReport::TradesSearchByLogin(const void *param1,const void *param2)
  {
   return(*((int *)param1)-((TradeRecord *)param2)->login);
  }
//+------------------------------------------------------------------+
