//+------------------------------------------------------------------+
//|                                               Raw Reports plugin |
//|                   Copyright 2001-2014, MetaQuotes Software Corp. |
//|                                        http://www.metaquotes.net |
//+------------------------------------------------------------------+
#include "stdafx.h"
#include "ReportOrders.h"
//+------------------------------------------------------------------+
//| Orders Report                                                    |
//+------------------------------------------------------------------+
BOOL CReportOrders::GenerateHTML(const ReportParams* params)
  {
   char tmp[256]="",num_fmt[128]="";
   int  i,result=TRUE;
//--- checks
   if(params==NULL)                                   return(FALSE);
   if(params->trades==NULL || params->trades_total<1) return(FALSE);
   if(params->filepath[0]==0)                         return(FALSE);
//--- open file
   if(m_file!=NULL) fclose(m_file);
   if((m_file=fopen(params->filepath,"wt"))==NULL)    return(FALSE);
//--- generation
   WriteHeader(m_info.name);
//--- pt styles
   fprintf(m_file,"<style>\n"
                  ".money { mso-number-format:\\#\\,\\#\\#0\\.00; }\n"
                  ".lots  { mso-number-format:0\\.00; }\n"
                  ".dt    { mso-number-format:\"yyyy\\.mm\\.dd hh\\:mm\"; }\n"
                  ".pt0   {mso-number-format:0;}\n"
                  ".pt1   {mso-number-format:0\\.0;}\n"
                  ".pt2   {mso-number-format:0\\.00;}\n"
                  ".pt3   {mso-number-format:0\\.000;}\n"
                  ".pt4   {mso-number-format:0\\.0000;}\n"
                  ".pt5   {mso-number-format:0\\.00000;}\n"
                  ".pt6   {mso-number-format:0\\.000000;}\n"
                  ".pt7   {mso-number-format:0\\.0000000;}\n"
                  ".pt8   {mso-number-format:0\\.00000000;}\n"
                  "</style>\n");
//--- report header
   fprintf(m_file,"<div align=center>\n");
   fprintf(m_file,"<table cellspacing=1 cellpadding=2 border=0 width=99%%>\n");
   fprintf(m_file,"<tr><td colspan=19><font size=2><b>%s</b></font></td></tr>",m_info.name);
   fprintf(m_file,"<tr align=right bgcolor=#c0c0c0>");
   fprintf(m_file,"<td align=left>Deal</td><td align=left>Login</td><td>Time</td><td>Type</td>"
                  "<td>Symbol</td><td>Volume</td><td>Price</td><td>S/L</td><td>T/P</td><td>Price</td><td>Reason</td>"
                  "<td>Gateway Order</td><td>Gateway Volume</td><td>Open Price Delta</td><td>Close Price Delta</td>"
                  "<td>Commission</td><td>Taxes</td><td>Swap</td><td>Profit</td><td>Comment</td>");
   fprintf(m_file,"</tr>\n");
//--- report rows
   TradeRecord *record=params->trades;
   for(i=0;i<params->trades_total;i++,record++)
     {
      //--- background color
      if((i&1)==0) fprintf(m_file,"<tr align=right>");
      else         fprintf(m_file,"<tr align=right bgcolor=#e0e0e0>");
      //--- price format
      if(record->digits<0 || record->digits>8) { COPY_STR(num_fmt,"class=pt4") }
      else StringCchPrintfA(num_fmt,sizeof(num_fmt)-1,"class=pt%d",record->digits);
      //--- row
      fprintf(m_file,"<td align=left>%d</td>",record->order);
      fprintf(m_file,"<td align=left>%d</td>",record->login);
      fprintf(m_file,"<td nowrap class=dt>%s</td>",FormatDateTime(record->open_time,tmp,sizeof(tmp)-1));
      fprintf(m_file,"<td nowrap>%s</td>",GetCmd(record->cmd));
      COPY_STR(tmp,record->symbol); _strlwr(tmp);
      fprintf(m_file,"<td nowrap>%s</td>",tmp);
      fprintf(m_file,"<td nowrap>%s</td>",ToVolume(record->volume/100.0,tmp,sizeof(tmp)-1));
      ToSymExt(tmp,record->open_price,record->digits);
      fprintf(m_file,"<td %s>%s</td>",num_fmt,tmp);
      ToSym(tmp,sizeof(tmp)-1,record->sl,record->digits);
      fprintf(m_file,"<td %s>%s</td>",num_fmt,tmp);
      ToSym(tmp,sizeof(tmp)-1,record->tp,record->digits);
      fprintf(m_file,"<td %s>%s</td>",num_fmt,tmp);
      ToSym(tmp,sizeof(tmp)-1,record->close_price,record->digits);
      fprintf(m_file,"<td %s>%s</td>",num_fmt,tmp);
      fprintf(m_file,"<td nowrap>%s</td>",FormatOrderReason(record->reason,tmp,sizeof(tmp)-1));
      if(record->gw_order>0)
         fprintf(m_file,"<td>%d</td>",record->gw_order);
      else
         fprintf(m_file,"<td></td>");
      if(record->gw_volume>0)
         fprintf(m_file,"<td nowrap>%s</td>",ToVolume(record->gw_volume/100.0,tmp,sizeof(tmp)-1));
      else
         fprintf(m_file,"<td></td>");
      if(record->gw_open_price!=0)
         fprintf(m_file,"<td>%i</td>",record->gw_open_price);
      else
         fprintf(m_file,"<td></td>");
      if(record->gw_close_price!=0)
         fprintf(m_file,"<td>%i</td>",record->gw_close_price);
      else
         fprintf(m_file,"<td></td>");
      if(record->cmd<=OP_SELL)
        {
         fprintf(m_file,"<td class=money nowrap>%s</td>",ToMoney(record->commission,2,tmp,sizeof(tmp)-1));
         fprintf(m_file,"<td class=money nowrap>%s</td>",ToMoney(record->taxes     ,2,tmp,sizeof(tmp)-1));
         fprintf(m_file,"<td class=money nowrap>%s</td>",ToMoney(record->storage   ,2,tmp,sizeof(tmp)-1));
         fprintf(m_file,"<td class=money nowrap>%s</td>",ToMoney(record->profit    ,2,tmp,sizeof(tmp)-1));
        }
      else
         fprintf(m_file,"<td colspan=4>&nbsp;</td>");
      fprintf(m_file,"<td nowrap>%s</td>",record->comment);
      fprintf(m_file,"</tr>\n");
      //--- report progress and check cancellation
      if((i&7)==0 && params->fn_progress!=NULL)
         if(params->fn_progress(params->custom,i,params->trades_total)!=0)
           {
            result=FALSE; break;
           }
      //---
     }
   fprintf(m_file,"</table>\n</div>\n");
   fprintf(m_file,"</body></html>\n");
   fclose(m_file);
//---
   return(result);
  }
//+------------------------------------------------------------------+
//|                                                                  |
//+------------------------------------------------------------------+
BOOL CReportOrders::GenerateCSV(const ReportParams* params)
  {
   char tmp[256]="";
   int  i,result=TRUE;
//--- checks
   if(params==NULL)                                   return(FALSE);
   if(params->trades==NULL || params->trades_total<1) return(FALSE);
   if(params->filepath[0]==0)                         return(FALSE);
//--- open file
   if(m_file!=NULL) fclose(m_file);
   if((m_file=fopen(params->filepath,"wt"))==NULL)    return(FALSE);
//---
   fprintf(m_file,"%s\n",m_info.name);
//--- report header
   fprintf(m_file,"Deal;Login;Time;Type;Symbol;Volume;Price;S/L;T/P;Price;Reason;"
                  "Gateway Order;Gateway Volume;Open Price Delta;Close Price Delta;"
                  "Commission;Taxes;Swap;Profit;Comment\n");
//--- report rows
   TradeRecord *record=params->trades;
   for(i=0;i<params->trades_total;i++,record++)
     {
      //--- row
      fprintf(m_file, "%d;%d;", record->order, record->login);
      FormatDateTime(record->open_time,tmp,sizeof(tmp)-1);
      fprintf(m_file,"%s;",tmp);
      fprintf(m_file,"%s;",GetCmd(record->cmd));
      strcpy(tmp,record->symbol); _strlwr(tmp);
      fprintf(m_file,"%s;",tmp);
      fprintf(m_file,"%.2lf;", record->volume/100.0);
      ToSymExt(tmp,record->open_price,record->digits);
      fprintf(m_file,"%s;", tmp);
      ToSym(tmp,sizeof(tmp)-1,record->sl,record->digits);
      fprintf(m_file,"%s;", tmp);
      ToSym(tmp,sizeof(tmp)-1,record->tp,record->digits);
      fprintf(m_file,"%s;", tmp);
      ToSym(tmp,sizeof(tmp)-1,record->close_price,record->digits);
      fprintf(m_file,"%s;", tmp);
      fprintf(m_file,"%s;",FormatOrderReason(record->reason,tmp,sizeof(tmp)-1));
      if(record->gw_order>0)
         fprintf(m_file,"%d;",record->gw_order);
      else
         fprintf(m_file,";");
      if(record->gw_volume>0)
         fprintf(m_file,"%s;",ToVolume(record->gw_volume/100.0,tmp,sizeof(tmp)-1));
      else
         fprintf(m_file,";");
      if(record->gw_open_price!=0)
         fprintf(m_file,"%i;",record->gw_open_price);
      else
         fprintf(m_file,";");
      if(record->gw_close_price!=0)
         fprintf(m_file,"%i;",record->gw_close_price);
      else
         fprintf(m_file,";");
      if(record->cmd<=OP_SELL)
         fprintf(m_file,"%.2lf;%.2lf;%.2lf;%.2lf;",record->commission,record->taxes,record->storage,record->profit);
      else
         fprintf(m_file,";;;;");
      fprintf(m_file,"%s\n",record->comment);
      //--- report progress and check cancellation
      if((i&7)==0 && params->fn_progress!=NULL)
         if(params->fn_progress(params->custom,i,params->trades_total)!=0)
           {
            result=FALSE; break;
           }
     }
   fclose(m_file);
//---
   return(result);
  }
//+------------------------------------------------------------------+
//|                                                                  |
//+------------------------------------------------------------------+
