//+------------------------------------------------------------------+
//|                                        Additional reports plugin |
//|                   Copyright 2001-2014, MetaQuotes Software Corp. |
//|                                        http://www.metaquotes.net |
//+------------------------------------------------------------------+
#include "stdafx.h"
#include "ReportClosedTrades.h"
//+------------------------------------------------------------------+
//| Closed Trades Report                                             |
//+------------------------------------------------------------------+
BOOL CReportClosedTrades::GenerateHTML(const ReportParams* params)
  {
   char    tmp[256]="",num_fmt[32]="";
   int     i,total_count=0,result=TRUE;
   __int64 lots=0;
   double  agents=.0,mul,pips,swaps=.0,profit=.0,commissions=.0,taxes=.0,profit_pips=.0;
   const UserRecord *ur =NULL;
//--- checks
   if(Startup(params)==FALSE) return(FALSE);
//--- body
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
//--- report header
   fprintf(m_file,"<div align=center>\n");
   fprintf(m_file,"<table cellspacing=1 cellpadding=2 border=0 width=\"99%%\">\n");
   fprintf(m_file,"<tr><td colspan=17><font size=2><b>Closed Trades Report</b> for '%s'",params->group.name);
   FormatDateTime(params->group.from,tmp,sizeof(tmp)-1,FALSE);
   fprintf(m_file," from %s",tmp);
   FormatDateTime(params->group.to-1,tmp,sizeof(tmp)-1,FALSE);
   fprintf(m_file," to %s",tmp);
   fprintf(m_file,"</font></td></tr>\n");
   fprintf(m_file,"<tr bgcolor=\"#c0c0c0\" align=right>");
   fprintf(m_file,"<td align=left>Deal</td><td align=left>Login</td><td>Name</td><td nowrap>Open Time</td><td>Type</td><td>Symbol</td>"
                  "<td>Volume</td><td nowrap>Open Price</td><td nowrap>Close Time</td><td nowrap>Close Price</td>"
                  "<td>Commission</td><td>Taxes</td><td>Agent</td><td>Swap</td><td>Profit</td><td>Pips</td><td>Comment</td>");
   fprintf(m_file,"</tr>\n");
//--- report rows
   TradeRecord *record=params->trades;
   for(i=0;i<params->trades_total;i++,record++)
     {
      if(record->login<1 || record->cmd>OP_SELL)         continue;
      if((ur=UserRecordGet(params,record->login))==NULL) continue;
      //--- background color
      if((total_count&1)==0) fprintf(m_file,"<tr align=right>");
      else                   fprintf(m_file,"<tr align=right bgcolor=\"#e0e0e0\">");
      //--- price format
      if(record->digits<0 || record->digits>8) { COPY_STR(num_fmt,"class=pt4") }
      else StringCchPrintfA(num_fmt,sizeof(num_fmt)-1,"class=pt%d",record->digits);
      //--- row
      fprintf(m_file,"<td align=left>%d</td>",record->order);
      fprintf(m_file,"<td align=left>%d</td>",record->login);
      fprintf(m_file,"<td align=left nowrap>%s</td>",ur->name);
      fprintf(m_file,"<td nowrap class=dt>%s</td>",FormatDateTime(record->open_time,tmp,sizeof(tmp)-1));
      fprintf(m_file,"<td nowrap>%s</td>",GetCmd(record->cmd));
      COPY_STR(tmp,record->symbol); _strlwr(tmp);
      fprintf(m_file,"<td nowrap>%s</td>",tmp);
      fprintf(m_file,"<td nowrap>%s</td>",ToVolume(record->volume/100.0,tmp,sizeof(tmp)-1));
      ToSymExt(tmp,record->open_price,record->digits);
      fprintf(m_file,"<td %s>%s</td>",num_fmt,tmp);
      fprintf(m_file,"<td nowrap class=dt>%s</td>",FormatDateTime(record->close_time,tmp,sizeof(tmp)-1));
      ToSym(tmp,sizeof(tmp)-1,record->close_price,record->digits);
      fprintf(m_file,"<td %s>%s</td>",num_fmt,tmp);
      fprintf(m_file,"<td nowrap class=money>%s</td>",ToMoney(record->commission      ,2,tmp,sizeof(tmp)-1));
      fprintf(m_file,"<td nowrap class=money>%s</td>",ToMoney(record->taxes           ,2,tmp,sizeof(tmp)-1));
      fprintf(m_file,"<td nowrap class=money>%s</td>",ToMoney(record->commission_agent,2,tmp,sizeof(tmp)-1));
      fprintf(m_file,"<td nowrap class=money>%s</td>",ToMoney(record->storage         ,2,tmp,sizeof(tmp)-1));
      //--- profits
      fprintf(m_file,"<td nowrap class=money>%s</td>",ToMoney(record->profit,2,tmp,sizeof(tmp)-1));
      mul=Decimals(record->digits);
      if(record->cmd==OP_BUY) pips=NormalizeDouble(record->close_price*mul,0)-NormalizeDouble(record->open_price *mul,0);
      else                    pips=NormalizeDouble(record->open_price *mul,0)-NormalizeDouble(record->close_price*mul,0);
      fprintf(m_file,"<td nowrap>%d</td>",int(pips));
      fprintf(m_file,"<td nowrap>%s</td>",record->comment);
      //---
      fprintf(m_file,"</tr>\n");
      //--- total
      commissions=NormalizeDouble(commissions+record->commission,2);
      taxes      =NormalizeDouble(taxes      +record->taxes,2);
      agents     =NormalizeDouble(agents     +record->commission_agent,2);
      swaps      =NormalizeDouble(swaps      +record->storage,2);
      profit     =NormalizeDouble(profit     +record->profit,2);
      profit_pips=NormalizeDouble(profit_pips+pips,0);
      lots       +=record->volume;
      total_count++;
      //--- report progress and check cancellation
      if((total_count&7)==0 && params->fn_progress!=NULL)
         if(params->fn_progress(params->custom,i,params->trades_total)!=0)
           {
            result=FALSE;
            break;
           }
     }
//--- total
   fprintf(m_file,"<tr bgcolor=\"#c0c0c0\" align=right><td colspan=6 align=left><b>Summary:</b></td>");
   fprintf(m_file,"<td nowrap class=money><b>%s</b></td>",ToMoney(lots/100.0,2,tmp,sizeof(tmp)-1));
   fprintf(m_file,"<td colspan=3>&nbsp;</td>");
   fprintf(m_file,"<td nowrap class=money><b>%s</b></td>",ToMoney(commissions,2,tmp,sizeof(tmp)-1));
   fprintf(m_file,"<td nowrap class=money><b>%s</b></td>",ToMoney(taxes      ,2,tmp,sizeof(tmp)-1));
   fprintf(m_file,"<td nowrap class=money><b>%s</b></td>",ToMoney(agents     ,2,tmp,sizeof(tmp)-1));
   fprintf(m_file,"<td nowrap class=money><b>%s</b></td>",ToMoney(swaps      ,2,tmp,sizeof(tmp)-1));
   fprintf(m_file,"<td nowrap class=money><b>%s</b></td>",ToMoney(profit     ,2,tmp,sizeof(tmp)-1));
   fprintf(m_file,"<td nowrap><b>%d</b></td>",int(profit_pips));
   fprintf(m_file,"<td>&nbsp;</td></tr>\n");
   fprintf(m_file,"</table>\n</div>\n");
   fprintf(m_file,"</body></html>\n");
   fclose(m_file);
   m_file=NULL;
//---
   return(result);
  }
//+------------------------------------------------------------------+
//|                                                                  |
//+------------------------------------------------------------------+
BOOL CReportClosedTrades::GenerateCSV(const ReportParams* params)
  {
   char    tmp[256]="";
   int     i,total_count=0,result=TRUE;
   __int64 lots=0;
   double  agents=0,mul,pips,comm=.0,swaps=.0,taxes=.0,profit=.0,profit_pips=0;
   const UserRecord *ur=NULL;
//--- checks
   if(Startup(params)==FALSE) return(FALSE);
//--- report header
   fprintf(m_file,"Closed Trades Report for \'%s\'",params->group.name);
   FormatDateTime(params->group.from,tmp,sizeof(tmp)-1,FALSE);
   fprintf(m_file," from %s",tmp);
   FormatDateTime(params->group.to-1,tmp,sizeof(tmp)-1,FALSE);
   fprintf(m_file," to %s\n",tmp);
   fprintf(m_file,"Deal;Login;Name;Open Time;Type;Symbol;Volume;Open Price;Close Time;Close Price;"
                  "Commission;Taxes;Agent;Swap;Profit;Pips;Comment\n");
//--- report rows
   TradeRecord *record=params->trades;
   for(i=0;i<params->trades_total;i++,record++)
     {
      if(record->login<1 || record->cmd>OP_SELL)         continue;
      if((ur=UserRecordGet(params,record->login))==NULL) continue;
      //--- row
      fprintf(m_file,"%d;",record->order);
      fprintf(m_file,"%d;",record->login);
      fprintf(m_file,"%s;",ur->name);
      FormatDateTime(record->open_time,tmp,sizeof(tmp)-1);
      fprintf(m_file,"%s;",tmp);
      fprintf(m_file,"%s;",GetCmd(record->cmd));
      COPY_STR(tmp,record->symbol); _strlwr(tmp);
      fprintf(m_file,"%s;",tmp);
      fprintf(m_file,"%.2lf;",record->volume/100.0);
      ToSymExt(tmp,record->open_price,record->digits);
      fprintf(m_file,"%s;",tmp);
      FormatDateTime(record->close_time,tmp,sizeof(tmp)-1);
      fprintf(m_file,"%s;",tmp);
      ToSym(tmp,sizeof(tmp)-1,record->close_price,record->digits);
      fprintf(m_file,"%s;",tmp);
      fprintf(m_file,"%.2lf;",record->commission);
      fprintf(m_file,"%.2lf;",record->taxes);
      fprintf(m_file,"%.2lf;",record->commission_agent);
      fprintf(m_file,"%.2lf;",record->storage);
      //--- profits
      fprintf(m_file,"%.2lf;",record->profit);
      mul=Decimals(record->digits);
      if(record->cmd==OP_BUY) pips=NormalizeDouble(record->close_price*mul,0)-NormalizeDouble(record->open_price *mul,0);
      else                    pips=NormalizeDouble(record->open_price *mul,0)-NormalizeDouble(record->close_price*mul,0);
      fprintf(m_file,"%d;",int(pips));
      fprintf(m_file,"%s\n",record->comment);
      //--- total
      comm       =NormalizeDouble(comm       +record->commission,2);
      taxes      =NormalizeDouble(taxes      +record->taxes,2);
      agents     =NormalizeDouble(agents     +record->commission_agent,2);
      swaps      =NormalizeDouble(swaps      +record->storage,2);
      profit     =NormalizeDouble(profit     +record->profit,2);
      profit_pips=NormalizeDouble(profit_pips+pips,0);
      lots       +=record->volume;
      total_count++;
      //--- report progress and check cancellation
      if((total_count&7)==0 && params->fn_progress!=NULL)
         if(params->fn_progress(params->custom,i,params->trades_total)!=0)
           {
            result=FALSE;
            break;
           }
     }
//--- total
   fprintf(m_file,";;;;;Summary:;%.2lf;;;;%.2lf;%.2lf;%.2lf;%.2lf;%.2lf;",lots/100.0,comm,taxes,agents,swaps,profit);
   fprintf(m_file,"%d\n",int(profit_pips));
   fclose(m_file);
   m_file=NULL;
//---
   return(result);
  }
//+------------------------------------------------------------------+
//|                                                                  |
//+------------------------------------------------------------------+
