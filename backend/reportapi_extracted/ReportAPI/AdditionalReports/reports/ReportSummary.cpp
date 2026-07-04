//+------------------------------------------------------------------+
//|                                        Additional reports plugin |
//|                   Copyright 2001-2014, MetaQuotes Software Corp. |
//|                                        http://www.metaquotes.net |
//+------------------------------------------------------------------+
#include "stdafx.h"
#include "ReportSummary.h"
//+------------------------------------------------------------------+
//|                                                                  |
//+------------------------------------------------------------------+
int CReportSummary::GenerateHTML(const ReportParams *params)
  {
   char              tmp[256]="";
   int               i,j,total_count=0,result=TRUE;
   __int64           total_lots=0;
   double            total_balance=.0,total_deposit=.0,total_withdraw=.0,total_credit=.0;
   double            total_comm=.0,total_swap=.0,total_taxes=.0,total_agent=.0,total_profit=.0;
   const UserRecord *ur=NULL;
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
   fprintf(m_file,"<tr><td colspan=12><font size=2><b>%s</b> for '%s'",m_info.name,params->group.name);
   FormatDateTime(params->group.from,tmp,sizeof(tmp)-1,FALSE); fprintf(m_file," from %s",tmp);
   FormatDateTime(params->group.to-1,tmp,sizeof(tmp)-1,FALSE); fprintf(m_file," to %s",tmp);
   fprintf(m_file,"</font></td></tr>\n");
//---
   fprintf(m_file,"<tr bgcolor=\"#c0c0c0\" align=right>");
   fprintf(m_file,"<td align=left>Login</td>"
                  "<td align=left>Name</td>"
                  "<td>Deposit</td>"
                  "<td>Withdraw</td>"
                  "<td>In/Out</td>"
                  "<td>Credit</td>"
                  "<td>Volume</td>"
                  "<td>Commission</td>"
                  "<td>Taxes</td>"
                  "<td>Agent</td>"
                  "<td>Storage</td>"
                  "<td>Profit</td>"
                  "<td nowrap>Last Balance</td></tr>\n");
//--- for each user
   for(i=0;i<params->group.total;i++)
     {
      if((ur=UserRecordGet(params,params->group_logins[i]))==NULL) continue;
      //---
      __int64 lots  =0;
      double  profit=0,comm=0,swap=0,taxes=0,agent=0,deposit=0,withdraw=0,credit=0;
      //--- collect data
      TradeRecord *trades=params->trades;
      for(j=0;j<params->trades_total;j++,trades++)
        {
         if(trades->login!=ur->login)                      continue;
         if(trades->cmd>OP_SELL && trades->cmd<OP_BALANCE) continue;  // skip pending orders
         //---
         if(trades->cmd==OP_BALANCE)
           {
            if(trades->profit>0) deposit =NormalizeDouble(deposit +trades->profit,2);
            else                 withdraw=NormalizeDouble(withdraw+trades->profit,2);
           }
         else
            if(trades->cmd==OP_CREDIT) credit=NormalizeDouble(credit+trades->profit,2);
            else // OP_BUY,OP_SELL
              {
               lots  +=trades->volume;
               profit=NormalizeDouble(profit+trades->profit,2);
               swap  =NormalizeDouble(swap  +trades->storage,2);
               comm  =NormalizeDouble(comm  +trades->commission,2);
               taxes =NormalizeDouble(taxes +trades->taxes,2);
               agent =NormalizeDouble(agent +trades->commission_agent,2);
              }
        }
      //--- background color
      if((total_count&1)==0) fprintf(m_file,"<tr align=right>");
      else                   fprintf(m_file,"<tr align=right bgcolor=\"#e0e0e0\">");
      //--- row
      fprintf(m_file,"<td align=left>%d</td>",params->group_logins[i]);
      fprintf(m_file,"<td nowrap align=left>%s</td>",ur==NULL ? "unknown":ur->name);
      fprintf(m_file,"<td nowrap class=money>%s</td>",ToMoney(deposit         ,2,tmp,sizeof(tmp)-1));
      fprintf(m_file,"<td nowrap class=money>%s</td>",ToMoney(withdraw        ,2,tmp,sizeof(tmp)-1));
      fprintf(m_file,"<td nowrap class=money>%s</td>",ToMoney(deposit+withdraw,2,tmp,sizeof(tmp)-1));
      fprintf(m_file,"<td nowrap class=money>%s</td>",ToMoney(credit          ,2,tmp,sizeof(tmp)-1));
      fprintf(m_file,"<td nowrap class=money>%s</td>",ToMoney(lots/100.0      ,2,tmp,sizeof(tmp)-1));
      fprintf(m_file,"<td nowrap class=money>%s</td>",ToMoney(comm            ,2,tmp,sizeof(tmp)-1));
      fprintf(m_file,"<td nowrap class=money>%s</td>",ToMoney(taxes           ,2,tmp,sizeof(tmp)-1));
      fprintf(m_file,"<td nowrap class=money>%s</td>",ToMoney(agent           ,2,tmp,sizeof(tmp)-1));
      fprintf(m_file,"<td nowrap class=money>%s</td>",ToMoney(swap            ,2,tmp,sizeof(tmp)-1));
      fprintf(m_file,"<td nowrap class=money>%s</td>",ToMoney(profit          ,2,tmp,sizeof(tmp)-1));
      fprintf(m_file,"<td nowrap class=money>%s</td>",ToMoney(ur->balance     ,2,tmp,sizeof(tmp)-1));
      fprintf(m_file,"</tr>\n");
      //--- total
      total_balance =NormalizeDouble(total_balance +ur->balance,2);
      total_deposit =NormalizeDouble(total_deposit +deposit,2);
      total_withdraw=NormalizeDouble(total_withdraw+withdraw,2);
      total_credit  =NormalizeDouble(total_credit  +credit,2);
      total_lots    +=lots;
      total_profit  =NormalizeDouble(total_profit  +profit,2);
      total_swap    =NormalizeDouble(total_swap    +swap,2);
      total_comm    =NormalizeDouble(total_comm    +comm,2);
      total_taxes   =NormalizeDouble(total_taxes   +taxes,2);
      total_agent   =NormalizeDouble(total_agent   +agent,2);
      total_count++;
      //--- report progress and check cancellation
      if((total_count&7)==0 && params->fn_progress!=NULL)
         if(params->fn_progress(params->custom,i,params->group.total)!=0)
           {
            result=FALSE;
            break;
           }
     }
//--- total
   fprintf(m_file,"<tr bgcolor=\"#c0c0c0\" align=right>");
   fprintf(m_file,"<td colspan=2>&nbsp;</td>");
   fprintf(m_file,"<td nowrap class=money>%s</td>",ToMoney(total_deposit               ,2,tmp,sizeof(tmp)-1));
   fprintf(m_file,"<td nowrap class=money>%s</td>",ToMoney(total_withdraw              ,2,tmp,sizeof(tmp)-1));
   fprintf(m_file,"<td nowrap class=money>%s</td>",ToMoney(total_deposit+total_withdraw,2,tmp,sizeof(tmp)-1));
   fprintf(m_file,"<td nowrap class=money>%s</td>",ToMoney(total_credit                ,2,tmp,sizeof(tmp)-1));
   fprintf(m_file,"<td nowrap class=money>%s</td>",ToMoney(total_lots/100.0            ,2,tmp,sizeof(tmp)-1));
   fprintf(m_file,"<td nowrap class=money>%s</td>",ToMoney(total_comm                  ,2,tmp,sizeof(tmp)-1));
   fprintf(m_file,"<td nowrap class=money>%s</td>",ToMoney(total_taxes                 ,2,tmp,sizeof(tmp)-1));
   fprintf(m_file,"<td nowrap class=money>%s</td>",ToMoney(total_agent                 ,2,tmp,sizeof(tmp)-1));
   fprintf(m_file,"<td nowrap class=money>%s</td>",ToMoney(total_swap                  ,2,tmp,sizeof(tmp)-1));
   fprintf(m_file,"<td nowrap class=money>%s</td>",ToMoney(total_profit                ,2,tmp,sizeof(tmp)-1));
   fprintf(m_file,"<td nowrap class=money>%s</td>",ToMoney(total_balance               ,2,tmp,sizeof(tmp)-1));
   fprintf(m_file,"</tr>\n");
   fprintf(m_file,"<tr bgcolor=\"#c0c0c0\" align=right>");
   fprintf(m_file,"<td align=left colspan=2><b>Summary:</b></td>");
   fprintf(m_file,"<td nowrap class=money><b>%s</b></td>",ToMoney(total_deposit               ,2,tmp,sizeof(tmp)-1));
   fprintf(m_file,"<td nowrap class=money><b>%s</b></td>",ToMoney(total_withdraw              ,2,tmp,sizeof(tmp)-1));
   fprintf(m_file,"<td nowrap class=money><b>%s</b></td>",ToMoney(total_deposit+total_withdraw,2,tmp,sizeof(tmp)-1));
   fprintf(m_file,"<td nowrap class=money><b>%s</b></td>",ToMoney(total_credit                ,2,tmp,sizeof(tmp)-1));
   fprintf(m_file,"<td nowrap class=money><b>%s</b></td>",ToMoney(total_lots/100.0            ,2,tmp,sizeof(tmp)-1));
   fprintf(m_file,"<td nowrap class=money colspan=5><b>%s</b></td>",ToMoney(total_comm+total_taxes+total_swap+total_profit,2,tmp,sizeof(tmp)-1));
   fprintf(m_file,"<td nowrap class=money><b>%s</b></td>",ToMoney(total_balance,2,tmp,sizeof(tmp)-1));
   fprintf(m_file,"</table>\n</div>\n");
   fprintf(m_file,"</body></html>\n");
//--- close
   fclose(m_file);
   m_file=NULL;
//---
   return(result);
  }
//+------------------------------------------------------------------+
//|                                                                  |
//+------------------------------------------------------------------+
int CReportSummary::GenerateCSV(const ReportParams *params)
  {
   char              tmp[256]="";
   int               total_count=0,result=TRUE;
   __int64           total_lots=0;
   double            total_balance=.0,total_deposit=.0,total_withdraw=.0,total_credit=.0;
   double            total_comm=.0,total_swap=.0,total_taxes=.0,total_agent=.0,total_profit=.0;
   const UserRecord *ur=NULL;
//--- checks
   if(Startup(params)==FALSE) return(FALSE);
//--- report header
   fprintf(m_file,"%s for '%s'",m_info.name,params->group.name);
   FormatDateTime(params->group.from,tmp,sizeof(tmp)-1,FALSE); fprintf(m_file," from %s",tmp);
   FormatDateTime(params->group.to-1,tmp,sizeof(tmp)-1,FALSE); fprintf(m_file," to %s\n",tmp);
//---
   fprintf(m_file,"Login;Name;Deposit;Withdraw;In/Out;Credit;Volume;Commission;Taxes;Agent;Storage;Profit;Last Balance\n");
//--- for each login
   for(int i=0;i<params->group.total;i++)
     {
      if((ur=UserRecordGet(params, params->group_logins[i]))==NULL) continue;
      //---
      __int64 lots  =0;
      double  profit=0,comm=0,swap=0,taxes=0,agent=0,deposit=0,withdraw=0,credit=0;
      //--- collect data
      TradeRecord *trades=params->trades;
      for(int j=0;j<params->trades_total;j++,trades++)
        {
         if(params->trades[j].login!=params->group_logins[i])                  continue;
         if(params->trades[j].cmd>OP_SELL && params->trades[j].cmd<OP_BALANCE) continue;
         //---
         if(params->trades[j].cmd==OP_BALANCE)
           {
            if(params->trades[j].profit>0) deposit =NormalizeDouble(deposit +params->trades[j].profit,2);
            else                           withdraw=NormalizeDouble(withdraw+params->trades[j].profit,2);
           }
         else if(params->trades[j].cmd==OP_CREDIT)
              {
               credit=NormalizeDouble(credit+params->trades[j].profit,2);
              }
            else // OP_BUY,OP_SELL
              {
               lots  +=params->trades[j].volume;
               profit=NormalizeDouble(profit+params->trades[j].profit,2);
               swap  =NormalizeDouble(swap  +params->trades[j].storage,2);
               comm  =NormalizeDouble(comm  +params->trades[j].commission,2);
               taxes =NormalizeDouble(taxes +params->trades[j].taxes,2);
               agent =NormalizeDouble(agent +params->trades[j].commission_agent,2);
              }
        }
      //--- row
      fprintf(m_file,"%d;",params->group_logins[i]);
      fprintf(m_file,"%s;",ur==NULL?"unknown":ur->name);
      fprintf(m_file,"%.2lf;",deposit);
      fprintf(m_file,"%.2lf;",withdraw);
      fprintf(m_file,"%.2lf;",deposit+withdraw);
      fprintf(m_file,"%.2lf;",credit);
      fprintf(m_file,"%.2lf;",lots/100.0);
      fprintf(m_file,"%.2lf;",comm);
      fprintf(m_file,"%.2lf;",taxes);
      fprintf(m_file,"%.2lf;",agent);
      fprintf(m_file,"%.2lf;",swap);
      fprintf(m_file,"%.2lf;",profit);
      fprintf(m_file,"%.2lf\n",ur->balance);
      //--- total
      total_balance =NormalizeDouble(total_balance +ur->balance,2);
      total_deposit =NormalizeDouble(total_deposit +deposit,2);
      total_withdraw=NormalizeDouble(total_withdraw+withdraw,2);
      total_credit  =NormalizeDouble(total_credit  +credit,2);
      total_lots    +=lots;
      total_profit  =NormalizeDouble(total_profit  +profit,2);
      total_swap    =NormalizeDouble(total_swap    +swap,2);
      total_comm    =NormalizeDouble(total_comm    +comm,2);
      total_taxes   =NormalizeDouble(total_taxes   +taxes,2);
      total_agent   =NormalizeDouble(total_agent   +agent,2);
      total_count++;
      //--- report progress and check cancellation
      if((total_count&7)==0 && params->fn_progress!=NULL)
         if(params->fn_progress(params->custom,i,params->group.total)!=0)
           {
            result=FALSE;
            break;
           }
     }
//--- total
   fprintf(m_file,";;");
   fprintf(m_file,"%.2lf;",total_deposit);
   fprintf(m_file,"%.2lf;",total_withdraw);
   fprintf(m_file,"%.2lf;",total_deposit+total_withdraw);
   fprintf(m_file,"%.2lf;",total_credit);
   fprintf(m_file,"%.2lf;",total_lots/100.0);
   fprintf(m_file,"%.2lf;",total_comm);
   fprintf(m_file,"%.2lf;",total_taxes);
   fprintf(m_file,"%.2lf;",total_agent);
   fprintf(m_file,"%.2lf;",total_swap);
   fprintf(m_file,"%.2lf;",total_profit);
   fprintf(m_file,"%.2lf\n",total_balance);
   fprintf(m_file,";Summary:;");
   fprintf(m_file,"%.2lf;",total_deposit);
   fprintf(m_file,"%.2lf;",total_withdraw);
   fprintf(m_file,"%.2lf;",total_deposit+total_withdraw);
   fprintf(m_file,"%.2lf;",total_credit);
   fprintf(m_file,"%.2lf;",total_lots/100.0);
   fprintf(m_file,";;;;%.2lf;",total_comm+total_taxes+total_swap+total_profit);
   fprintf(m_file,"%.2lf\n",total_balance);
//--- close
   fclose(m_file);
   m_file=NULL;
//---
   return(result);
  }
//+------------------------------------------------------------------+
