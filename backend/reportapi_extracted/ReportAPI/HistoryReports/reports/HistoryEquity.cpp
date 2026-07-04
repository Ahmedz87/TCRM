//+------------------------------------------------------------------+
//|                                                   Reports plugin |
//|                   Copyright 2001-2014, MetaQuotes Software Corp. |
//|                                        http://www.metaquotes.net |
//+------------------------------------------------------------------+
#include "stdafx.h"
#include "HistoryEquity.h"
//+------------------------------------------------------------------+
//| Sort DailyRecord by bank-group-login                             |
//+------------------------------------------------------------------+
static int SortDailyEquity(const void *left,const void *right)
  {
   DailyReport *lhs=(DailyReport*)left,*rhs=(DailyReport*)right;
//---
   int res=strcmp(lhs->bank,rhs->bank);
   if(res==0) res=strcmp(lhs->group,rhs->group);
   if(res==0) res=lhs->login-rhs->login;
//---
   return(res);
  }
//+------------------------------------------------------------------+
//| Equity Report                                                    |
//+------------------------------------------------------------------+
BOOL CHistoryEquity::GenerateHTML(const ReportParams* params)
  {
   DailyReport *daily=NULL,daily_total={0},daily_bank={0};
   int          total=0,total_bank,i,result=TRUE;
   char         tmp[256]="",lastbank[sizeof(daily_bank.bank)]="";
//--- checks
   if(params==NULL)                                   return(FALSE);
   if(params->buffer==NULL || params->buffer_size<1)  return(FALSE);
   if(params->filepath[0]==0)                         return(FALSE);
   if((total=params->buffer_size/sizeof(daily[0]))<1) return(FALSE);
//--- sorting
   daily=(DailyReport*)params->buffer;
   if(total>1) qsort(daily,total,sizeof(daily[0]),SortDailyEquity);
//--- open file
   if(m_file!=NULL) fclose(m_file);
   if((m_file=fopen(params->filepath,"wt"))==NULL)    return(FALSE);
//--- generation
   WriteHeader(m_info.name);
   fprintf(m_file,"<style>\n"
                  ".money { mso-number-format:\\#\\,\\#\\#0\\.00; }\n"
                  "</style>\n");
//--- report header
   fprintf(m_file,"<div align=center>\n");
   fprintf(m_file,"<table cellspacing=1 cellpadding=2 border=0 width=\"99%%\">\n");
   fprintf(m_file,"<tr><td colspan=12><font size=2><b>Equity Report</b> for '%s'",params->group.name);
   FormatDateTime(params->group.from,tmp,sizeof(tmp)-1,FALSE);
   fprintf(m_file," from %s",tmp);
   FormatDateTime(params->group.to-1,tmp,sizeof(tmp)-1,FALSE);
   fprintf(m_file," to %s",tmp);
   fprintf(m_file,"</font></td></tr>\n");
//---
   fprintf(m_file,"<tr align=right bgcolor=\"#c0c0c0\">"
                  "<td align=left>Login</td><td align=left>Group</td><td nowrap>PL Balance</td>"
                  "<td nowrap>Closed PL</td><td>Deposit</td><td>Balance</td><td nowrap>Floating PL</td>"
                  "<td>Credit</td><td>Equity</td><td>Margin</td><td nowrap>Free Margin</td><td>Bank</td>"
                  "</tr>\n");
//--- for each bank
   for(i=0,total_bank=0;i<total;i++,daily++)
     {
      TERMINATE_STR(daily->bank);
      fprintf(m_file,"<tr align=right>");
      fprintf(m_file,"<td align=left>%d</td>",       daily->login);
      fprintf(m_file,"<td align=left nowrap>%s</td>",daily->group);
      fprintf(m_file,"<td nowrap class=money>%s</td>",ToMoney(daily->balance_prev ,2,tmp,sizeof(tmp)-1));
      fprintf(m_file,"<td nowrap class=money>%s</td>",ToMoney(daily->profit_closed,2,tmp,sizeof(tmp)-1));
      fprintf(m_file,"<td nowrap class=money>%s</td>",ToMoney(daily->deposit      ,2,tmp,sizeof(tmp)-1));
      fprintf(m_file,"<td nowrap class=money>%s</td>",ToMoney(daily->balance      ,2,tmp,sizeof(tmp)-1));
      fprintf(m_file,"<td nowrap class=money>%s</td>",ToMoney(daily->profit       ,2,tmp,sizeof(tmp)-1));
      fprintf(m_file,"<td nowrap class=money>%s</td>",ToMoney(daily->credit       ,2,tmp,sizeof(tmp)-1));
      fprintf(m_file,"<td nowrap class=money>%s</td>",ToMoney(daily->equity       ,2,tmp,sizeof(tmp)-1));
      fprintf(m_file,"<td nowrap class=money>%s</td>",ToMoney(daily->margin       ,2,tmp,sizeof(tmp)-1));
      fprintf(m_file,"<td nowrap class=money>%s</td>",ToMoney(daily->margin_free  ,2,tmp,sizeof(tmp)-1));
      if(daily->bank[0]!=0) fprintf(m_file,"<td nowrap>%s</td>",daily->bank);
      else                  fprintf(m_file,"<td>&nbsp;</td>");
      fprintf(m_file,"</tr>\n");
      //--- collect
      total_bank++;
      daily_bank.balance_prev =NormalizeDouble(daily_bank.balance_prev +daily->balance_prev,2);
      daily_bank.profit_closed=NormalizeDouble(daily_bank.profit_closed+daily->profit_closed,2);
      daily_bank.deposit      =NormalizeDouble(daily_bank.deposit      +daily->deposit,2);
      daily_bank.balance      =NormalizeDouble(daily_bank.balance      +daily->balance,2);
      daily_bank.profit       =NormalizeDouble(daily_bank.profit       +daily->profit,2);
      daily_bank.credit       =NormalizeDouble(daily_bank.credit       +daily->credit,2);
      daily_bank.equity       =NormalizeDouble(daily_bank.equity       +daily->equity,2);
      daily_bank.margin       =NormalizeDouble(daily_bank.margin       +daily->margin,2);
      daily_bank.margin_free  =NormalizeDouble(daily_bank.margin_free  +daily->margin_free,2);
      //---
      daily_total.balance_prev =NormalizeDouble(daily_total.balance_prev +daily->balance_prev,2);
      daily_total.profit_closed=NormalizeDouble(daily_total.profit_closed+daily->profit_closed,2);
      daily_total.deposit      =NormalizeDouble(daily_total.deposit      +daily->deposit,2);
      daily_total.balance      =NormalizeDouble(daily_total.balance      +daily->balance,2);
      daily_total.profit       =NormalizeDouble(daily_total.profit       +daily->profit,2);
      daily_total.credit       =NormalizeDouble(daily_total.credit       +daily->credit,2);
      daily_total.equity       =NormalizeDouble(daily_total.equity       +daily->equity,2);
      daily_total.margin       =NormalizeDouble(daily_total.margin       +daily->margin,2);
      daily_total.margin_free  =NormalizeDouble(daily_total.margin_free  +daily->margin_free,2);
      //---
      COPY_STR(lastbank,daily->bank);
      //---
      if((i+1)>=total || strcmp((daily+1)->bank,lastbank)!=0)
        {
         //--- total for bank
         fprintf(m_file,"<tr align=right>");
         fprintf(m_file,"<td align=left><b>%d</b></td>",total_bank);
         fprintf(m_file,"<td align=left><b>&nbsp;</b></td>");
         fprintf(m_file,"<td nowrap class=money><b>%s</b></td>",ToMoney(daily_bank.balance_prev ,2,tmp,sizeof(tmp)-1));
         fprintf(m_file,"<td nowrap class=money><b>%s</b></td>",ToMoney(daily_bank.profit_closed,2,tmp,sizeof(tmp)-1));
         fprintf(m_file,"<td nowrap class=money><b>%s</b></td>",ToMoney(daily_bank.deposit      ,2,tmp,sizeof(tmp)-1));
         fprintf(m_file,"<td nowrap class=money><b>%s</b></td>",ToMoney(daily_bank.balance      ,2,tmp,sizeof(tmp)-1));
         fprintf(m_file,"<td nowrap class=money><b>%s</b></td>",ToMoney(daily_bank.profit       ,2,tmp,sizeof(tmp)-1));
         fprintf(m_file,"<td nowrap class=money><b>%s</b></td>",ToMoney(daily_bank.credit       ,2,tmp,sizeof(tmp)-1));
         fprintf(m_file,"<td nowrap class=money><b>%s</b></td>",ToMoney(daily_bank.equity       ,2,tmp,sizeof(tmp)-1));
         fprintf(m_file,"<td nowrap class=money><b>%s</b></td>",ToMoney(daily_bank.margin       ,2,tmp,sizeof(tmp)-1));
         fprintf(m_file,"<td nowrap class=money><b>%s</b></td>",ToMoney(daily_bank.margin_free  ,2,tmp,sizeof(tmp)-1));
         fprintf(m_file,"<td><b>&nbsp;</b></td>");
         fprintf(m_file,"</tr>\n");
         memset(&daily_bank,0,sizeof(daily_bank));
         total_bank=0;
        }
      //--- report progress and check cancellation
      if((i&7)==0 && params->fn_progress!=NULL)
         if(params->fn_progress(params->custom,i,total)!=0)
           {
            result=FALSE; break;
           }
      //---
     }
//--- total
   fprintf(m_file,"<tr bgcolor=\"#c0c0c0\" align=right>");
   fprintf(m_file,"<td align=left><b>%d</b></td>",total);
   fprintf(m_file,"<td align=left><b>&nbsp;</b></td>");
   fprintf(m_file,"<td nowrap class=money><b>%s</b></td>",ToMoney(daily_total.balance_prev ,2,tmp,sizeof(tmp)-1));
   fprintf(m_file,"<td nowrap class=money><b>%s</b></td>",ToMoney(daily_total.profit_closed,2,tmp,sizeof(tmp)-1));
   fprintf(m_file,"<td nowrap class=money><b>%s</b></td>",ToMoney(daily_total.deposit      ,2,tmp,sizeof(tmp)-1));
   fprintf(m_file,"<td nowrap class=money><b>%s</b></td>",ToMoney(daily_total.balance      ,2,tmp,sizeof(tmp)-1));
   fprintf(m_file,"<td nowrap class=money><b>%s</b></td>",ToMoney(daily_total.profit       ,2,tmp,sizeof(tmp)-1));
   fprintf(m_file,"<td nowrap class=money><b>%s</b></td>",ToMoney(daily_total.credit       ,2,tmp,sizeof(tmp)-1));
   fprintf(m_file,"<td nowrap class=money><b>%s</b></td>",ToMoney(daily_total.equity       ,2,tmp,sizeof(tmp)-1));
   fprintf(m_file,"<td nowrap class=money><b>%s</b></td>",ToMoney(daily_total.margin       ,2,tmp,sizeof(tmp)-1));
   fprintf(m_file,"<td nowrap class=money><b>%s</b></td>",ToMoney(daily_total.margin_free  ,2,tmp,sizeof(tmp)-1));
   fprintf(m_file,"<td><b>&nbsp;</b></td>");
   fprintf(m_file,"</tr>\n");
//---
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
BOOL CHistoryEquity::GenerateCSV(const ReportParams* params)
  {
   DailyReport *daily=NULL,daily_total={0},daily_bank={0};
   int          total=0,total_bank,i,result=TRUE;
   char         tmp[256]="",lastbank[sizeof(daily_bank.bank)]="";
//--- checks
   if(params==NULL)                                   return(FALSE);
   if(params->buffer==NULL || params->buffer_size<1)  return(FALSE);
   if(params->filepath[0]==0)                         return(FALSE);
   if((total=params->buffer_size/sizeof(daily[0]))<1) return(FALSE);
//--- sorting
   daily=(DailyReport*)params->buffer;
   if(total>1) qsort(daily,total,sizeof(daily[0]),SortDailyEquity);
//--- open file
   if(m_file!=NULL) fclose(m_file);
   if((m_file=fopen(params->filepath,"wt"))==NULL)    return(FALSE);
//--- report header
   fprintf(m_file,"Equity Report for '%s'",params->group.name);
   FormatDateTime(params->group.from,tmp,sizeof(tmp)-1,FALSE);
   fprintf(m_file," from %s",tmp);
   FormatDateTime(params->group.to-1,tmp,sizeof(tmp)-1,FALSE);
   fprintf(m_file," to %s\n",tmp);
   fprintf(m_file,"Login;Group;PL Balance;Closed PL;Deposit;Balance;Floating PL;"
               "Credit;Equity;Margin;Free Margin;Bank\n");
//--- for each bank
   for(i=0,total_bank=0;i<total;i++,daily++)
     {
      fprintf(m_file,"%d;%s;",daily->login,daily->group);
      fprintf(m_file,"%.2lf;",daily->balance_prev);
      fprintf(m_file,"%.2lf;%.2lf;",daily->profit_closed,daily->deposit);
      fprintf(m_file,"%.2lf;%.2lf;",daily->balance,daily->profit);
      fprintf(m_file,"%.2lf;%.2lf;",daily->credit,daily->equity);
      fprintf(m_file,"%.2lf;%.2lf;",daily->margin,daily->margin_free);
      if(daily->bank[0]!=0) fprintf(m_file,"%s;",daily->bank);
      else                    fprintf(m_file,";");
      fprintf(m_file,"\n");
      //--- collect
      total_bank++;
      daily_bank.balance_prev =NormalizeDouble(daily_bank.balance_prev +daily->balance_prev,2);
      daily_bank.profit_closed=NormalizeDouble(daily_bank.profit_closed+daily->profit_closed,2);
      daily_bank.deposit      =NormalizeDouble(daily_bank.deposit      +daily->deposit,2);
      daily_bank.balance      =NormalizeDouble(daily_bank.balance      +daily->balance,2);
      daily_bank.profit       =NormalizeDouble(daily_bank.profit       +daily->profit,2);
      daily_bank.credit       =NormalizeDouble(daily_bank.credit       +daily->credit,2);
      daily_bank.equity       =NormalizeDouble(daily_bank.equity       +daily->equity,2);
      daily_bank.margin       =NormalizeDouble(daily_bank.margin       +daily->margin,2);
      daily_bank.margin_free  =NormalizeDouble(daily_bank.margin_free  +daily->margin_free,2);
      //---
      daily_total.balance_prev =NormalizeDouble(daily_total.balance_prev +daily->balance_prev,2);
      daily_total.profit_closed=NormalizeDouble(daily_total.profit_closed+daily->profit_closed,2);
      daily_total.deposit      =NormalizeDouble(daily_total.deposit      +daily->deposit,2);
      daily_total.balance      =NormalizeDouble(daily_total.balance      +daily->balance,2);
      daily_total.profit       =NormalizeDouble(daily_total.profit       +daily->profit,2);
      daily_total.credit       =NormalizeDouble(daily_total.credit       +daily->credit,2);
      daily_total.equity       =NormalizeDouble(daily_total.equity       +daily->equity,2);
      daily_total.margin       =NormalizeDouble(daily_total.margin       +daily->margin,2);
      daily_total.margin_free  =NormalizeDouble(daily_total.margin_free  +daily->margin_free,2);
      //---
      COPY_STR(lastbank,daily->bank);
      //---
      if((i+1)>=total || strcmp((daily+1)->bank,lastbank)!=0)
        {
         //--- total for bank
         fprintf(m_file,"%d;;",total_bank);
         fprintf(m_file,"%.2lf;",daily_bank.balance_prev);
         fprintf(m_file,"%.2lf;%.2lf;",daily_bank.profit_closed,daily_bank.deposit);
         fprintf(m_file,"%.2lf;%.2lf;",daily_bank.balance,daily_bank.profit);
         fprintf(m_file,"%.2lf;%.2lf;",daily_bank.credit,daily_bank.equity);
         fprintf(m_file,"%.2lf;%.2lf;",daily_bank.margin,daily_bank.margin_free);
         fprintf(m_file,";;\n");
         memset(&daily_bank,0,sizeof(daily_bank));
         total_bank=0;
        }
      //--- report progress and check cancellation
      if((i&7)==0 && params->fn_progress!=NULL)
         if(params->fn_progress(params->custom,i,total)!=0)
           {
            result=FALSE; break;
           }
      //---
     }
//--- total
   fprintf(m_file,"%d;;",total);
   fprintf(m_file,"%.2lf;",daily_total.balance_prev);
   fprintf(m_file,"%.2lf;%.2lf;",daily_total.profit_closed,daily_total.deposit);
   fprintf(m_file,"%.2lf;%.2lf;",daily_total.balance,daily_total.profit);
   fprintf(m_file,"%.2lf;%.2lf;",daily_total.credit,daily_total.equity);
   fprintf(m_file,"%.2lf;%.2lf;",daily_total.margin,daily_total.margin_free);
   fprintf(m_file,";;\n");
//---
   fclose(m_file);
   m_file=NULL;
//---
   return(result);
  }
//+------------------------------------------------------------------+
//|                                                                  |
//+------------------------------------------------------------------+
