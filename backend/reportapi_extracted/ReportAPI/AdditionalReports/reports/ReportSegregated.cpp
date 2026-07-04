//+------------------------------------------------------------------+
//|                                        Additional reports plugin |
//|                   Copyright 2001-2014, MetaQuotes Software Corp. |
//|                                        http://www.metaquotes.net |
//+------------------------------------------------------------------+
#include "stdafx.h"
#include "ReportSegregated.h"
//+------------------------------------------------------------------+
//| Segregated Report                                                |
//+------------------------------------------------------------------+
BOOL CReportSegregated::GenerateHTML(const ReportParams* params)
  {
   char               tmp[256]="";
   int                i,j,total_margin=0,total_count=0,result=TRUE;
   const UserRecord  *ur    =NULL;
   const MarginLevel *margin=NULL;
   UserRecord         user={0};
   double             total_balance=0,total_interest=0,total_tax=0,total_credit=0;
   double             total_comm=0,total_swap=0,total_taxes=0,total_profit=0,total_pl=0,total_equity=0;
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
   fprintf(m_file,"<tr><td colspan=12><font size=2><b>Segregated Report</b> for '%s'",params->group.name);
   FormatDateTime(params->group.from,tmp,sizeof(tmp)-1,FALSE);
   fprintf(m_file," from %s",tmp);
   FormatDateTime(params->group.to-1,tmp,sizeof(tmp)-1,FALSE);
   fprintf(m_file," to %s",tmp);
   fprintf(m_file,"</font></td></tr>\n");
//---
   fprintf(m_file,"<tr bgcolor=\"#c0c0c0\" align=right>");
   fprintf(m_file,"<td align=left>Login</td>"
                  "<td align=left>Name</td>"
                  "<td>Balance</td>"
                  "<td>Credit</td>"
                  "<td>Commissions</td>"
                  "<td>Taxes</td>"
                  "<td>Storage</td>"
                  "<td>Profit</td>"
                  "<td>Interest</td>"
                  "<td>Tax</td>"
                  "<td nowrap>Unrealized P/L</td>"
                  "<td>Equity</td>\n");
//--- for each login
   margin      =(const MarginLevel*)params->buffer;
   total_margin=params->buffer_size/sizeof(margin[0]);
   for(i=0;i<params->group.total;i++)
     {
      double profit=0,comm=0,swap=0,taxes=0,interest=0,tax=0,pl=0;
      int    login=params->group_logins[i];
      //---
      if((ur=UserRecordGet(params,params->group_logins[i]))==NULL) continue;
      //--- collect data
      for(j=0;j<params->trades_total;j++)
        {
         if(params->trades[j].login!=login) continue;
         if(params->trades[j].cmd>OP_SELL && params->trades[j].cmd<OP_BALANCE) continue;
         //---
         if(params->trades[j].cmd==OP_BALANCE)
           {
            if(_stricmp(params->trades[j].comment,"IR") ==0) { interest=NormalizeDouble(interest+params->trades[j].profit,2); continue; }
            if(_stricmp(params->trades[j].comment,"Tax")==0) { tax     =NormalizeDouble(tax     +params->trades[j].profit,2); continue; }
           }
         if(params->trades[j].cmd<OP_BUY_LIMIT)
           {
            profit=NormalizeDouble(profit+params->trades[j].profit,2);
            swap  =NormalizeDouble(swap  +params->trades[j].storage,2);
            comm  =NormalizeDouble(comm  +params->trades[j].commission,2);
            taxes =NormalizeDouble(taxes +params->trades[j].taxes,2);
           }
        }
      //---
      for(j=0;j<total_margin;j++)
        {
         if(margin[j].login==login)
           {
            pl=margin[j].equity-margin[j].balance;
            break;
           }
        }
      //--- background color
      if((total_count&1)==0) fprintf(m_file,"<tr align=right>");
      else                   fprintf(m_file,"<tr align=right bgcolor=\"#e0e0e0\">");
      //--- row
      fprintf(m_file,"<td align=left>%d</td>",params->group_logins[i]);
      fprintf(m_file,"<td align=left nowrap>%s</td>",ur->name);
      fprintf(m_file,"<td nowrap class=money>%s</td>",ToMoney(ur->balance,2,tmp,sizeof(tmp)-1));
      fprintf(m_file,"<td nowrap class=money>%s</td>",ToMoney(ur->credit ,2,tmp,sizeof(tmp)-1));
      fprintf(m_file,"<td nowrap class=money>%s</td>",ToMoney(comm       ,2,tmp,sizeof(tmp)-1));
      fprintf(m_file,"<td nowrap class=money>%s</td>",ToMoney(taxes      ,2,tmp,sizeof(tmp)-1));
      fprintf(m_file,"<td nowrap class=money>%s</td>",ToMoney(swap       ,2,tmp,sizeof(tmp)-1));
      fprintf(m_file,"<td nowrap class=money>%s</td>",ToMoney(profit     ,2,tmp,sizeof(tmp)-1));
      fprintf(m_file,"<td nowrap class=money>%s</td>",ToMoney(interest   ,2,tmp,sizeof(tmp)-1));
      fprintf(m_file,"<td nowrap class=money>%s</td>",ToMoney(tax        ,2,tmp,sizeof(tmp)-1));
      fprintf(m_file,"<td nowrap class=money>%s</td>",ToMoney(pl         ,2,tmp,sizeof(tmp)-1));
      fprintf(m_file,"<td nowrap class=money>%s</td>",ToMoney(ur->balance+ur->credit+pl,2,tmp,sizeof(tmp)-1));
      fprintf(m_file,"</tr>\n");
      //--- total
      total_balance =NormalizeDouble(total_balance +ur->balance,2);
      total_interest=NormalizeDouble(total_interest+interest,2);
      total_tax     =NormalizeDouble(total_tax     +tax,2);
      total_credit  =NormalizeDouble(total_credit  +ur->credit,2);
      total_comm    =NormalizeDouble(total_comm    +comm,2);
      total_swap    =NormalizeDouble(total_swap    +swap,2);
      total_taxes   =NormalizeDouble(total_taxes   +taxes,2);
      total_profit  =NormalizeDouble(total_profit  +profit,2);
      total_pl      =NormalizeDouble(total_pl      +pl,2);
      total_equity  =NormalizeDouble(total_equity  +ur->balance,2);
      total_equity  =NormalizeDouble(total_equity  +ur->credit,2);
      total_equity  =NormalizeDouble(total_equity  +pl,2);
      total_count++;
      //--- report progress and check cancellation
      if((total_count&7)==0 && params->fn_progress!=NULL)
         if(params->fn_progress(params->custom,i,params->group.total)!=0)
           {
            result=FALSE; break;
           }
     }
//--- total
   fprintf(m_file,"<tr bgcolor=\"#c0c0c0\" align=right>");
   fprintf(m_file,"<td align=left colspan=2><b>Summary:</td>");
   fprintf(m_file,"<td nowrap class=money><b>%s</b></td>",ToMoney(total_balance ,2,tmp,sizeof(tmp)-1));
   fprintf(m_file,"<td nowrap class=money><b>%s</b></td>",ToMoney(total_credit  ,2,tmp,sizeof(tmp)-1));
   fprintf(m_file,"<td nowrap class=money><b>%s</b></td>",ToMoney(total_comm    ,2,tmp,sizeof(tmp)-1));
   fprintf(m_file,"<td nowrap class=money><b>%s</b></td>",ToMoney(total_taxes   ,2,tmp,sizeof(tmp)-1));
   fprintf(m_file,"<td nowrap class=money><b>%s</b></td>",ToMoney(total_swap    ,2,tmp,sizeof(tmp)-1));
   fprintf(m_file,"<td nowrap class=money><b>%s</b></td>",ToMoney(total_profit  ,2,tmp,sizeof(tmp)-1));
   fprintf(m_file,"<td nowrap class=money><b>%s</b></td>",ToMoney(total_interest,2,tmp,sizeof(tmp)-1));
   fprintf(m_file,"<td nowrap class=money><b>%s</b></td>",ToMoney(total_tax     ,2,tmp,sizeof(tmp)-1));
   fprintf(m_file,"<td nowrap class=money><b>%s</b></td>",ToMoney(total_pl      ,2,tmp,sizeof(tmp)-1));
   fprintf(m_file,"<td nowrap class=money><b>%s</b></td>",ToMoney(total_equity  ,2,tmp,sizeof(tmp)-1));
   fprintf(m_file,"</tr>\n");
//--- house account
   fprintf(m_file,"<tr><td colspan=11><font size=2><b>House Account</b></font></td></tr>\n");
   for(i=0; i<params->users_total; i++)
     {
      if(strcmp(params->users[i].group,"house")!=0) continue;
      memcpy(&user,&params->users[i],sizeof(user));
      break;
     }
//---
   fprintf(m_file,"<tr bgcolor=\"#c0c0c0\" align=right>");
   if(user.login>0)
     {
      fprintf(m_file,"<td>%d</td>",user.login);
      fprintf(m_file,"<td align=left>%s</td>",user.name);
     }
   else fprintf(m_file,"<td colspan=2>&nbsp;</td>");
   fprintf(m_file,"<td nowrap class=money><b>%s</b></td>",ToMoney(user.balance   ,2,tmp,sizeof(tmp)-1));
   fprintf(m_file,"<td nowrap class=money><b>%s</b></td>",ToMoney(-total_credit  ,2,tmp,sizeof(tmp)-1));
   fprintf(m_file,"<td nowrap class=money><b>%s</b></td>",ToMoney(-total_comm    ,2,tmp,sizeof(tmp)-1));
   fprintf(m_file,"<td nowrap class=money><b>%s</b></td>",ToMoney(-total_taxes   ,2,tmp,sizeof(tmp)-1));
   fprintf(m_file,"<td nowrap class=money><b>%s</b></td>",ToMoney(-total_swap    ,2,tmp,sizeof(tmp)-1));
   fprintf(m_file,"<td nowrap class=money><b>%s</b></td>",ToMoney(-total_profit  ,2,tmp,sizeof(tmp)-1));
   fprintf(m_file,"<td nowrap class=money><b>%s</b></td>",ToMoney(-total_interest,2,tmp,sizeof(tmp)-1));
   fprintf(m_file,"<td nowrap class=money><b>%s</b></td>",ToMoney(-total_tax     ,2,tmp,sizeof(tmp)-1));
   fprintf(m_file,"<td nowrap class=money><b>%s</b></td>",ToMoney(-total_pl      ,2,tmp,sizeof(tmp)-1));
   fprintf(m_file,"<td nowrap class=money><b>%s</b></td>",
   ToMoney(user.balance-total_credit-total_comm-total_swap-total_interest-total_tax-total_pl,2,tmp,sizeof(tmp)-1));
   fprintf(m_file,"</tr>\n</table>\n</div>\n</body></html>\n");
//---
   fclose(m_file);
   m_file=NULL;
//---
   return(result);
  }
//+------------------------------------------------------------------+
//|                                                                  |
//+------------------------------------------------------------------+
BOOL CReportSegregated::GenerateCSV(const ReportParams* params)
  {
   char               tmp[256]="";
   int                i,j,total_margin=0,total_count=0,result=TRUE;
   const UserRecord  *ur    =NULL;
   const MarginLevel *margin=NULL;
   UserRecord         user={0};
   double             total_balance=0,total_interest=0,total_tax=0,total_credit=0;
   double             total_comm=0,total_swap=0,total_taxes=0,total_profit=0,total_pl=0,total_equity=0;
//--- checks
   if(Startup(params)==FALSE) return(FALSE);
//--- report header
   fprintf(m_file,"Segregated Report for '%s'",params->group.name);
   FormatDateTime(params->group.from,tmp,sizeof(tmp)-1,FALSE);
   fprintf(m_file," from %s",tmp);
   FormatDateTime(params->group.to-1,tmp,sizeof(tmp)-1,FALSE);
   fprintf(m_file," to %s\n",tmp);
//---
   fprintf(m_file,"Login;Name;Balance;Credit;Commissions;Taxes;Storage;Profit;Interest;Tax;Unrealized P/L;Equity\n");
//--- for each login
   margin      =(const MarginLevel*)params->buffer;
   total_margin=params->buffer_size/sizeof(margin[0]);
   for(i=0;i<params->group.total;i++)
     {
      double profit=0,comm=0,swap=0,taxes=0,interest=0,tax=0,pl=0;
      int    login=params->group_logins[i];
      //---
      if((ur=UserRecordGet(params,params->group_logins[i]))==NULL) continue;
      //--- collect data
      for(j=0;j<params->trades_total;j++)
        {
         if(params->trades[j].login!=login) continue;
         if(params->trades[j].cmd>OP_SELL && params->trades[j].cmd<OP_BALANCE) continue;
         //---
         if(params->trades[j].cmd==OP_BALANCE)
           {
            if(_stricmp(params->trades[j].comment,"IR") ==0) { interest=NormalizeDouble(interest+params->trades[j].profit,2); continue; }
            if(_stricmp(params->trades[j].comment,"Tax")==0) { tax     =NormalizeDouble(tax     +params->trades[j].profit,2); continue; }
           }
         if(params->trades[j].cmd<OP_BUY_LIMIT)
           {
            profit=NormalizeDouble(profit+params->trades[j].profit,2);
            swap  =NormalizeDouble(swap  +params->trades[j].storage,2);
            comm  =NormalizeDouble(comm  +params->trades[j].commission,2);
            taxes =NormalizeDouble(taxes +params->trades[j].taxes,2);
           }
        }
      //---
      for(j=0;j<total_margin;j++)
        {
         if(margin[j].login==login)
           {
            pl=margin[j].equity-margin[j].balance;
            break;
           }
        }
      //--- row
      fprintf(m_file,"%d;",params->group_logins[i]);
      fprintf(m_file,"%s;",ur->name);
      fprintf(m_file,"%.2lf;",ur->balance);
      fprintf(m_file,"%.2lf;",ur->credit);
      fprintf(m_file,"%.2lf;",comm);
      fprintf(m_file,"%.2lf;",taxes);
      fprintf(m_file,"%.2lf;",swap);
      fprintf(m_file,"%.2lf;",profit);
      fprintf(m_file,"%.2lf;",interest);
      fprintf(m_file,"%.2lf;",tax);
      fprintf(m_file,"%.2lf;",pl);
      fprintf(m_file,"%.2lf\n",ur->balance+ur->credit+pl);
      //--- total
      total_balance =NormalizeDouble(total_balance +ur->balance,2);
      total_interest=NormalizeDouble(total_interest+interest,2);
      total_tax     =NormalizeDouble(total_tax     +tax,2);
      total_credit  =NormalizeDouble(total_credit  +ur->credit,2);
      total_comm    =NormalizeDouble(total_comm    +comm,2);
      total_swap    =NormalizeDouble(total_swap    +swap,2);
      total_taxes   =NormalizeDouble(total_taxes   +taxes,2);
      total_profit  =NormalizeDouble(total_profit  +profit,2);
      total_pl      =NormalizeDouble(total_pl      +pl,2);
      total_equity  =NormalizeDouble(total_equity  +ur->balance,2);
      total_equity  =NormalizeDouble(total_equity  +ur->credit,2);
      total_equity  =NormalizeDouble(total_equity  +pl,2);
      total_count++;
      //--- report progress and check cancellation
      if((total_count&7)==0 && params->fn_progress!=NULL)
         if(params->fn_progress(params->custom,i,params->group.total)!=0)
           {
            result=FALSE; break;
           }
     }
//--- total
   fprintf(m_file,";Summary:;");
   fprintf(m_file,"%.2lf;",total_balance);
   fprintf(m_file,"%.2lf;",total_credit);
   fprintf(m_file,"%.2lf;",total_comm);
   fprintf(m_file,"%.2lf;",total_taxes);
   fprintf(m_file,"%.2lf;",total_swap);
   fprintf(m_file,"%.2lf;",total_profit);
   fprintf(m_file,"%.2lf;",total_interest);
   fprintf(m_file,"%.2lf;",total_tax);
   fprintf(m_file,"%.2lf;",total_pl);
   fprintf(m_file,"%.2lf\n",total_equity);
//--- house account
   fprintf(m_file,"House Account;;;;;;;;;;\n");
   for(i=0; i<params->users_total; i++)
     {
      if(strcmp(params->users[i].group,"house")!=0) continue;
      memcpy(&user,&params->users[i],sizeof(user));
      break;
     }
//---
   if(user.login>0) fprintf(m_file,"%d;",user.login);
   else             fprintf(m_file,";");
   fprintf(m_file,"%s;",user.name);
   fprintf(m_file,"%.2lf;",user.balance);
   fprintf(m_file,"%.2lf;",-total_credit);
   fprintf(m_file,"%.2lf;",-total_comm);
   fprintf(m_file,"%.2lf;",-total_taxes);
   fprintf(m_file,"%.2lf;",-total_swap);
   fprintf(m_file,"%.2lf;",-total_profit);
   fprintf(m_file,"%.2lf;",-total_interest);
   fprintf(m_file,"%.2lf;",-total_tax);
   fprintf(m_file,"%.2lf;",-total_pl);
   fprintf(m_file,"%.2lf\n",user.balance-total_credit-total_comm-total_swap-total_interest-total_tax-total_pl);
//---
   fclose(m_file);
   m_file=NULL;
//---
   return(result);
  }
//+------------------------------------------------------------------+
//|                                                                  |
//+------------------------------------------------------------------+
